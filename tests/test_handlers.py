import pytest

from app import commands
from app.config import Settings
from app.handlers import SkillHandler
from app.llm import AnswerResult
from app.protocol import parse_request
from app.storage import Storage
from app.weather import WEATHER_ASK_CITY, WEATHER_ERROR, Weather


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


def make_request(text="привет", is_new=False, user="u1", timezone="UTC", entities=None):
    payload = {
        "version": "1.0",
        "meta": {"timezone": timezone},
        "request": {
            "original_utterance": text,
            "type": "SimpleUtterance",
            "nlu": {"tokens": [], "entities": entities or []},
        },
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


class FakeWeather:
    def __init__(self, weather=None, error=None):
        self.weather = weather
        self.error = error
        self.cities = []

    async def get(self, city):
        self.cities.append(city)
        if self.error is not None:
            raise self.error
        return self.weather


def make_handler(storage, result=None, weather=None):
    if result is None:
        result = AnswerResult(text="ответ", is_pending=False)
    llm = FakeLlm(result)
    return SkillHandler(make_settings(), storage, llm, weather=weather), llm


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


async def test_weather_by_city(storage):
    weather = Weather(
        city="Москва", temperature=5, description="дождь", wind_speed=2, t_min=1, t_max=7
    )
    fake = FakeWeather(weather=weather)
    handler, llm = make_handler(storage, weather=fake)
    response = await handler.handle(make_request(text="погода в Москве"))
    assert "Москва" in response["response"]["text"]
    assert "дождь" in response["response"]["text"]
    assert fake.cities == ["москве"]
    assert llm.calls == []


async def test_weather_uses_stored_city(storage):
    storage.set_fact("u1", "city", "Казань")
    fake = FakeWeather(
        weather=Weather(city="Казань", temperature=1, description="снег", wind_speed=1)
    )
    handler, _ = make_handler(storage, weather=fake)
    await handler.handle(make_request(text="какая сегодня погода"))
    assert fake.cities == ["Казань"]


async def test_weather_asks_city_when_unknown(storage):
    fake = FakeWeather()
    handler, _ = make_handler(storage, weather=fake)
    response = await handler.handle(make_request(text="погода"))
    assert response["response"]["text"] == WEATHER_ASK_CITY
    assert storage.get_fact("u1", "awaiting_city") == "1"
    assert fake.cities == []


async def test_weather_remembers_city_from_followup(storage):
    storage.set_fact("u1", "awaiting_city", "1")
    fake = FakeWeather(
        weather=Weather(city="Сочи", temperature=20, description="ясно", wind_speed=2)
    )
    handler, _ = make_handler(storage, weather=fake)
    response = await handler.handle(make_request(text="Сочи"))
    assert storage.get_fact("u1", "city") == "Сочи"
    assert storage.get_fact("u1", "awaiting_city") == ""
    assert "Сочи" in response["response"]["text"]


async def test_weather_uses_nlu_entity_city(storage):
    fake = FakeWeather(
        weather=Weather(city="Сочи", temperature=20, description="ясно", wind_speed=2)
    )
    handler, _ = make_handler(storage, weather=fake)
    entities = [{"type": "YANDEX.GEO", "value": {"city": "Сочи"}}]
    await handler.handle(make_request(text="какая погода", entities=entities))
    assert fake.cities == ["Сочи"]


async def test_weather_error_is_handled(storage):
    fake = FakeWeather(error=RuntimeError("boom"))
    handler, _ = make_handler(storage, weather=fake)
    response = await handler.handle(make_request(text="погода в Москве"))
    assert response["response"]["text"] == WEATHER_ERROR


async def test_weather_disabled_falls_through_to_llm(storage):
    fake = FakeWeather()
    llm = FakeLlm(AnswerResult("ответ"))
    handler = SkillHandler(make_settings(weather_enabled=False), storage, llm, weather=fake)
    await handler.handle(make_request(text="погода в Москве"))
    assert fake.cities == []
    assert llm.calls


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
