import pytest

from app.personalization import (
    FactKind,
    facts_reply,
    format_facts_prompt,
    parse_fact_command,
)


@pytest.mark.parametrize(
    ("text", "kind", "value"),
    [
        ("меня зовут Иван", FactKind.NAME, "Иван"),
        ("Меня зовут Иван.", FactKind.NAME, "Иван"),
        ("моё имя Иван", FactKind.NAME, "Иван"),
        ("мое имя иван", FactKind.NAME, "иван"),
        ("запомни, меня зовут Иван", FactKind.NAME, "Иван"),
        ("Алиса, меня зовут Иван", FactKind.NAME, "Иван"),
        ("мой город Казань", FactKind.CITY, "Казань"),
        ("я живу в Казани", FactKind.CITY, "Казани"),
        ("я живу в городе Казань", FactKind.CITY, "Казань"),
        ("запомни: я люблю кофе", FactKind.NOTE, "я люблю кофе"),
        ("запомни, что я люблю кофе", FactKind.NOTE, "я люблю кофе"),
        ("что ты обо мне знаешь", FactKind.SHOW, None),
        ("что ты знаешь обо мне", FactKind.SHOW, None),
        ("забудь обо мне", FactKind.FORGET, None),
        ("забудь всё обо мне", FactKind.FORGET, None),
    ],
)
def test_parse_fact_command(text, kind, value):
    command = parse_fact_command(text)
    assert command is not None
    assert command.kind is kind
    assert command.value == value


def test_parse_returns_none_for_normal_question():
    assert parse_fact_command("расскажи анекдот") is None


def test_parse_returns_none_for_empty():
    assert parse_fact_command("") is None


def test_format_facts_prompt_empty():
    assert format_facts_prompt({}) == ""


def test_format_facts_prompt_includes_values():
    prompt = format_facts_prompt({"name": "Иван", "city": "Казань", "notes": "любит кофе"})
    assert "Известно о пользователе:" in prompt
    assert "Иван" in prompt
    assert "Казань" in prompt
    assert "любит кофе" in prompt


def test_facts_reply_without_facts():
    assert "ничего" in facts_reply({}).lower()


def test_facts_reply_lists_facts():
    reply = facts_reply({"name": "Иван", "city": "Казань"})
    assert "Иван" in reply
    assert "Казань" in reply
