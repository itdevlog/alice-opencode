import pytest

from app import commands
from app.config import Settings
from app.handlers import SkillHandler
from app.llm import AnswerResult
from app.protocol import parse_request
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


def make_request(text="привет", is_new=False, user="u1"):
    payload = {
        "version": "1.0",
        "request": {"original_utterance": text, "type": "SimpleUtterance"},
        "session": {
            "new": is_new,
            "session_id": "s1",
            "user": {"user_id": user},
            "application": {"application_id": "app"},
        },
    }
    return parse_request(payload)


class FakeLlm:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def answer(self, user_id, messages, deadline=None):
        self.calls.append((user_id, messages))
        return self.result


@pytest.fixture
def storage():
    store = Storage(":memory:")
    yield store
    store.close()


def make_handler(storage, result=None):
    if result is None:
        result = AnswerResult(text="ответ", is_pending=False)
    llm = FakeLlm(result)
    return SkillHandler(make_settings(), storage, llm), llm


async def test_new_empty_session_greets_without_calling_llm(storage):
    handler, llm = make_handler(storage)
    response = await handler.handle(make_request(text="", is_new=True))
    assert response["response"]["text"] == commands.GREETING_TEXT
    assert response["response"]["end_session"] is False
    assert llm.calls == []


async def test_help_command(storage):
    handler, llm = make_handler(storage)
    response = await handler.handle(make_request(text="помощь"))
    assert response["response"]["text"] == commands.HELP_TEXT
    assert llm.calls == []


async def test_clear_command_wipes_history(storage):
    storage.add_message("u1", "user", "старое")
    handler, _ = make_handler(storage)
    response = await handler.handle(make_request(text="очисти историю"))
    assert response["response"]["text"] == commands.CLEAR_TEXT
    assert storage.get_history("u1", limit=10) == []


async def test_exit_command_ends_session(storage):
    handler, _ = make_handler(storage)
    response = await handler.handle(make_request(text="выход"))
    assert response["response"]["text"] == commands.EXIT_TEXT
    assert response["response"]["end_session"] is True


async def test_question_calls_llm_with_system_history_and_stores_messages(storage):
    storage.add_message("u1", "user", "прошлое")
    handler, llm = make_handler(storage, AnswerResult(text="**Ответ**"))
    response = await handler.handle(make_request(text="вопрос"))

    assert response["response"]["text"] == "Ответ"
    assert response["response"]["tts"] == "Ответ"
    user_id, messages = llm.calls[0]
    assert user_id == "u1"
    assert messages[0] == {"role": "system", "content": "SYS"}
    assert messages[-1] == {"role": "user", "content": "вопрос"}
    assert storage.get_history("u1", limit=10) == [
        {"role": "user", "content": "прошлое"},
        {"role": "user", "content": "вопрос"},
        {"role": "assistant", "content": "**Ответ**"},
    ]


async def test_pending_result_returns_hint_and_does_not_store_assistant(storage):
    handler, _ = make_handler(storage, AnswerResult(text=None, is_pending=True))
    response = await handler.handle(make_request(text="сложный вопрос"))
    assert response["response"]["text"] == commands.PENDING_HINT
    assert storage.get_history("u1", limit=10) == [
        {"role": "user", "content": "сложный вопрос"}
    ]


async def test_ready_pending_is_delivered_and_popped(storage):
    storage.add_message("u1", "user", "сложный вопрос")
    storage.save_pending("u1", "сложный вопрос")
    storage.set_pending_answer("u1", "готовый ответ")
    handler, llm = make_handler(storage)
    response = await handler.handle(make_request(text="дальше"))
    assert response["response"]["text"] == "готовый ответ"
    assert storage.get_pending("u1") is None
    assert llm.calls == []


async def test_not_ready_pending_asks_to_wait(storage):
    storage.save_pending("u1", "вопрос")
    handler, llm = make_handler(storage)
    response = await handler.handle(make_request(text="ну что там"))
    assert response["response"]["text"] == commands.WAIT_TEXT
    assert llm.calls == []


async def test_continue_without_pending_is_handled(storage):
    handler, llm = make_handler(storage)
    response = await handler.handle(make_request(text="дальше"))
    assert llm.calls == []
    assert response["response"]["text"] != commands.WAIT_TEXT
