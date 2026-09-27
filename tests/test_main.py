import httpx
import pytest

from app.config import Settings
from app.llm import AnswerResult
from app.main import create_app
from app.storage import Storage


def make_settings(**overrides):
    base = {
        "opencode_api_key": "k",
        "opencode_base_url": "http://test/v1",
        "model": "m",
        "db_path": ":memory:",
        "skill_id": None,
        "request_deadline_seconds": 2.0,
        "max_tokens": 100,
        "history_limit": 10,
        "system_prompt": "SYS",
    }
    base.update(overrides)
    return Settings(**base)


class FakeLlm:
    def __init__(self, result):
        self.result = result

    async def answer(self, user_id, messages, deadline=None):
        return self.result


def make_payload(text="привет", user="u1", skill_id="skill-42"):
    return {
        "version": "1.0",
        "request": {"original_utterance": text, "type": "SimpleUtterance"},
        "session": {
            "new": False,
            "session_id": "s1",
            "skill_id": skill_id,
            "user": {"user_id": user},
            "application": {"application_id": "app"},
        },
    }


@pytest.fixture
def storage():
    store = Storage(":memory:")
    yield store
    store.close()


async def call_app(app, path="/alice", payload=None, method="post"):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, json=payload)


async def test_healthz(storage):
    app = create_app(make_settings(), storage=storage, llm=FakeLlm(AnswerResult("x")))
    response = await call_app(app, path="/healthz", method="get")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_post_alice_returns_model_answer(storage):
    app = create_app(
        make_settings(), storage=storage, llm=FakeLlm(AnswerResult(text="привет от модели"))
    )
    response = await call_app(app, payload=make_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["response"]["text"] == "привет от модели"
    assert body["response"]["end_session"] is False


async def test_post_alice_rejects_wrong_skill_id(storage):
    app = create_app(
        make_settings(skill_id="expected"),
        storage=storage,
        llm=FakeLlm(AnswerResult(text="x")),
    )
    response = await call_app(app, payload=make_payload(skill_id="other"))
    assert response.status_code == 403
