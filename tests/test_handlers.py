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


def make_request(text="привет", is_new=False, user="u1", timezone="UTC"):
    payload = {
        "version": "1.0",
        "meta": {"timezone": timezone},
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
    assert messages[0]["role"] == "system"
    assert "SYS" in messages[0]["content"]
    assert "Сейчас" in messages[0]["content"]
    assert messages[-1] == {"role": "user", "content": "вопрос"}
    assert storage.get_history("u1", limit=10) == [
        {"role": "user", "content": "прошлое"},
        {"role": "user", "content": "вопрос"},
        {"role": "assistant", "content": "**Ответ**"},
    ]


async def test_repeat_returns_last_assistant_answer(storage):
    storage.add_message("u1", "assistant", "прошлый ответ")
    handler, llm = make_handler(storage)
    response = await handler.handle(make_request(text="повтори"))
    assert response["response"]["text"] == "прошлый ответ"
    assert llm.calls == []


async def test_repeat_without_history(storage):
    handler, llm = make_handler(storage)
    response = await handler.handle(make_request(text="повтори"))
    assert "нечего" in response["response"]["text"].lower()
    assert llm.calls == []


async def test_style_command_sets_preference(storage):
    handler, llm = make_handler(storage)
    response = await handler.handle(make_request(text="короче"))
    assert storage.get_fact("u1", "style") == "short"
    assert response["response"]["text"] == commands.STYLE_SET_TEXT["short"]
    assert llm.calls == []


async def test_style_hint_is_injected_into_system_prompt(storage):
    storage.set_fact("u1", "style", "detailed")
    handler, llm = make_handler(storage)
    await handler.handle(make_request(text="вопрос"))
    _, messages = llm.calls[0]
    assert "подробн" in messages[0]["content"].lower()


async def test_pending_hint_has_pause_in_tts(storage):
    handler, _ = make_handler(storage, AnswerResult(text=None, is_pending=True))
    response = await handler.handle(make_request(text="сложный вопрос"))
    assert response["response"]["text"] == commands.PENDING_HINT
    assert "sil" in response["response"]["tts"]


async def test_pending_hint_uses_wait_sound_when_configured(storage):
    llm = FakeLlm(AnswerResult(text=None, is_pending=True))
    handler = SkillHandler(make_settings(wait_sound="dialogs-upload/sound.opus"), storage, llm)
    response = await handler.handle(make_request(text="сложный вопрос"))
    assert "speaker audio" in response["response"]["tts"]


async def test_name_command_saves_fact_without_llm(storage):
    handler, llm = make_handler(storage)
    response = await handler.handle(make_request(text="меня зовут Иван"))
    assert response["response"]["text"] == "Хорошо, буду звать тебя Иван."
    assert storage.get_fact("u1", "name") == "Иван"
    assert llm.calls == []


async def test_city_command_saves_fact(storage):
    handler, llm = make_handler(storage)
    await handler.handle(make_request(text="мой город Казань"))
    assert storage.get_fact("u1", "city") == "Казань"
    assert llm.calls == []


async def test_note_command_saves_note(storage):
    handler, _ = make_handler(storage)
    response = await handler.handle(make_request(text="запомни: я люблю кофе"))
    assert storage.get_fact("u1", "notes") == "я люблю кофе"
    assert response["response"]["text"] == "Запомнил."


async def test_forget_command_clears_facts(storage):
    storage.set_fact("u1", "name", "Иван")
    handler, _ = make_handler(storage)
    response = await handler.handle(make_request(text="забудь обо мне"))
    assert storage.get_facts("u1") == {}
    assert response["response"]["text"] == "Хорошо, я забыл всё, что знал о тебе."


async def test_show_facts_lists_known_facts(storage):
    storage.set_fact("u1", "name", "Иван")
    handler, llm = make_handler(storage)
    response = await handler.handle(make_request(text="что ты обо мне знаешь"))
    assert "Иван" in response["response"]["text"]
    assert llm.calls == []


async def test_known_facts_are_injected_into_system_prompt(storage):
    storage.set_fact("u1", "name", "Иван")
    handler, llm = make_handler(storage)
    await handler.handle(make_request(text="вопрос"))
    _, messages = llm.calls[0]
    assert "Иван" in messages[0]["content"]


async def test_system_prompt_includes_request_timezone(storage):
    handler, llm = make_handler(storage)
    await handler.handle(make_request(text="привет", timezone="Asia/Yekaterinburg"))
    _, messages = llm.calls[0]
    assert "(Asia/Yekaterinburg)" in messages[0]["content"]


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
