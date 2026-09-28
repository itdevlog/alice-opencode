import httpx
import pytest
import respx

from app.config import Settings
from app.llm import OpenCodeGoTransport

URL = "http://test.local/v1/chat/completions"

SSE_BODY = (
    'data: {"choices":[{"delta":{"content":"привет"}}]}\n\n'
    'data: {"choices":[{"delta":{"content":", мир"}}]}\n\n'
    "data: [DONE]\n\n"
)


def make_settings(**overrides):
    base = {
        "opencode_api_key": "test-key",
        "opencode_base_url": "http://test.local/v1",
        "model": "test-model",
        "db_path": ":memory:",
        "skill_id": None,
        "request_deadline_seconds": 2.0,
        "max_tokens": 100,
        "history_limit": 10,
        "system_prompt": "sys",
    }
    base.update(overrides)
    return Settings(**base)


@respx.mock
async def test_transport_sends_agent_headers_and_parses_stream():
    route = respx.post(URL).mock(
        return_value=httpx.Response(
            200, headers={"content-type": "text/event-stream"}, text=SSE_BODY
        )
    )
    async with httpx.AsyncClient() as client:
        transport = OpenCodeGoTransport(make_settings(), client=client)
        chunks = [chunk async for chunk in transport.stream([], session_id="user-1")]

    assert "".join(chunks) == "привет, мир"
    request = route.calls.last.request
    assert request.headers["user-agent"].startswith("alice-opencode")
    assert request.headers["x-opencode-session"] == "user-1"
    assert request.headers["accept"] == "text/event-stream"


@respx.mock
async def test_transport_surfaces_error_body():
    respx.post(URL).mock(
        return_value=httpx.Response(
            400, json={"error": {"code": "inference_failed", "message": "bad request"}}
        )
    )
    async with httpx.AsyncClient() as client:
        transport = OpenCodeGoTransport(make_settings(), client=client)
        with pytest.raises(RuntimeError) as excinfo:
            async for _ in transport.stream([{"role": "user", "content": "hi"}], session_id="s"):
                pass

    message = str(excinfo.value)
    assert "400" in message
    assert "inference_failed" in message
