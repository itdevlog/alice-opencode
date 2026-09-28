import pytest

from app.storage import Storage


@pytest.fixture
def storage(tmp_path):
    store = Storage(str(tmp_path / "alice.db"))
    yield store
    store.close()


def test_history_returns_messages_in_order(storage):
    storage.add_message("u1", "user", "привет")
    storage.add_message("u1", "assistant", "здравствуй")
    history = storage.get_history("u1", limit=10)
    assert history == [
        {"role": "user", "content": "привет"},
        {"role": "assistant", "content": "здравствуй"},
    ]


def test_history_respects_limit_and_keeps_newest(storage):
    for i in range(5):
        storage.add_message("u1", "user", f"m{i}")
    history = storage.get_history("u1", limit=2)
    assert history == [
        {"role": "user", "content": "m3"},
        {"role": "user", "content": "m4"},
    ]


def test_history_empty_for_unknown_user(storage):
    assert storage.get_history("nobody", limit=10) == []


def test_clear_history_affects_only_given_user(storage):
    storage.add_message("u1", "user", "a")
    storage.add_message("u2", "user", "b")
    storage.clear_history("u1")
    assert storage.get_history("u1", limit=10) == []
    assert storage.get_history("u2", limit=10) == [{"role": "user", "content": "b"}]


def test_pending_roundtrip(storage):
    storage.save_pending("u1", "сложный вопрос")
    pending = storage.get_pending("u1")
    assert pending is not None
    assert pending.question == "сложный вопрос"
    assert pending.answer is None
    assert pending.is_ready is False


def test_pending_answer_set(storage):
    storage.save_pending("u1", "вопрос")
    storage.set_pending_answer("u1", "ответ")
    pending = storage.get_pending("u1")
    assert pending.answer == "ответ"
    assert pending.is_ready is True


def test_pop_pending_removes_it(storage):
    storage.save_pending("u1", "вопрос")
    storage.set_pending_answer("u1", "ответ")
    popped = storage.pop_pending("u1")
    assert popped.answer == "ответ"
    assert storage.get_pending("u1") is None


def test_pop_pending_returns_none_when_absent(storage):
    assert storage.pop_pending("none") is None


def test_set_and_get_facts(storage):
    storage.set_fact("u1", "name", "Иван")
    storage.set_fact("u1", "city", "Казань")
    assert storage.get_facts("u1") == {"name": "Иван", "city": "Казань"}


def test_get_fact_returns_none_when_absent(storage):
    storage.set_fact("u1", "name", "Иван")
    assert storage.get_fact("u1", "name") == "Иван"
    assert storage.get_fact("u1", "city") is None


def test_set_fact_overwrites(storage):
    storage.set_fact("u1", "name", "Иван")
    storage.set_fact("u1", "name", "Пётр")
    assert storage.get_fact("u1", "name") == "Пётр"


def test_delete_facts_affects_only_given_user(storage):
    storage.set_fact("u1", "name", "Иван")
    storage.set_fact("u2", "name", "Пётр")
    storage.delete_facts("u1")
    assert storage.get_facts("u1") == {}
    assert storage.get_facts("u2") == {"name": "Пётр"}
