import asyncio

import pytest

from app.config import Settings
from app.llm import AnswerResult, LlmService, extract_delta, usable_partial
from app.storage import Storage


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


class FakeTransport:
    def __init__(self, chunks, delay=0.0, error=None):
        self.chunks = chunks
        self.delay = delay
        self.error = error

    async def stream(self, messages, session_id="test"):
        if self.error is not None:
            if self.delay:
                await asyncio.sleep(self.delay)
            raise self.error
        for chunk in self.chunks:
            if self.delay:
                await asyncio.sleep(self.delay)
            yield chunk


@pytest.fixture
def storage():
    store = Storage(":memory:")
    yield store
    store.close()


def test_extract_delta_parses_content():
    line = 'data: {"choices":[{"delta":{"content":"привет"}}]}'
    assert extract_delta(line) == "привет"


def test_extract_delta_returns_none_for_done():
    assert extract_delta("data: [DONE]") is None


def test_extract_delta_returns_none_for_empty_line():
    assert extract_delta("") is None


def test_extract_delta_returns_none_for_non_data_line():
    assert extract_delta("event: message") is None


def test_extract_delta_returns_none_without_content():
    line = 'data: {"choices":[{"delta":{"role":"assistant"}}]}'
    assert extract_delta(line) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", False),
        ("коротко", False),
        ("Это целое предложение из достаточного числа символов!", True),
        ("x" * 200, True),
        ("Это длинное предложение без знака в конце но короткое", False),
    ],
)
def test_usable_partial(text, expected):
    assert usable_partial(text) is expected


async def test_slow_answer_returns_usable_partial_and_remainder(storage):
    sentence = "Погода сегодня обещает быть тёплой и солнечной."
    transport = FakeTransport(
        [sentence, " Обещают до плюс двадцати.", " Хорошего дня!"], delay=0.03
    )
    settings = make_settings(request_deadline_seconds=0.05)
    service = LlmService(settings, storage, transport=transport)

    result = await service.answer("u1", [{"role": "user", "content": "q"}])
    assert result.is_pending is False
    assert result.text == sentence

    await service.wait_background()
    pending = storage.get_pending("u1")
    assert pending is not None
    assert pending.answer == "Обещают до плюс двадцати. Хорошего дня!"


async def test_answer_returns_full_text_when_fast(storage):
    transport = FakeTransport(["Привет", ", мир", "!"])
    service = LlmService(make_settings(), storage, transport=transport)
    result = await service.answer("u1", [{"role": "user", "content": "hi"}])
    assert result == AnswerResult(text="Привет, мир!", is_pending=False)


async def test_slow_answer_becomes_pending_and_finishes_in_background(storage):
    transport = FakeTransport(["дол", "гий", " ответ"], delay=0.2)
    settings = make_settings(request_deadline_seconds=0.05)
    service = LlmService(settings, storage, transport=transport)

    result = await service.answer("u1", [{"role": "user", "content": "hi"}])
    assert result.is_pending is True
    assert result.text is None

    await service.wait_background()
    pending = storage.get_pending("u1")
    assert pending is not None
    assert pending.answer == "долгий ответ"
    assert pending.is_ready is True


async def test_transport_error_returns_error_text(storage):
    transport = FakeTransport([], error=RuntimeError("boom"))
    service = LlmService(make_settings(), storage, transport=transport)
    result = await service.answer("u1", [{"role": "user", "content": "hi"}])
    assert result.is_pending is False
    assert "не получилось" in result.text.lower()


async def test_background_error_stores_error_text(storage):
    transport = FakeTransport([], delay=0.2, error=RuntimeError("boom"))
    settings = make_settings(request_deadline_seconds=0.05)
    service = LlmService(settings, storage, transport=transport)
    await service.answer("u1", [{"role": "user", "content": "hi"}])
    await service.wait_background()
    assert "не получилось" in storage.get_pending("u1").answer.lower()
