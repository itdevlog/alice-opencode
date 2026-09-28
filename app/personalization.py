import re
from dataclasses import dataclass
from enum import StrEnum

NAME_SAVED = "Хорошо, буду звать тебя {name}."
CITY_SAVED = "Запомнил: ты в {city}."
NOTE_SAVED = "Запомнил."
FORGET_FACTS_TEXT = "Хорошо, я забыл всё, что знал о тебе."
NO_FACTS_TEXT = "Я пока ничего о тебе не знаю."
FACTS_HEADER = "Вот что я о тебе знаю:"

_LABELS = {"name": "имя", "city": "город", "notes": "заметки", "style": "стиль ответов"}

_STYLE_HINTS = {
    "short": "Отвечай максимально кратко — одним-двумя предложениями.",
    "detailed": "Отвечай подробно и развёрнуто, до шести-восьми предложений.",
    "normal": "Отвечай в обычном объёме — двумя-четырьмя предложениями.",
}


class FactKind(StrEnum):
    NAME = "name"
    CITY = "city"
    NOTE = "note"
    SHOW = "show"
    FORGET = "forget"


@dataclass
class FactCommand:
    kind: FactKind
    value: str | None = None


_NAME = re.compile(r"^(?:запомни,?\s*)?(?:меня зовут|мо[её] имя)\s+(.+)$", re.IGNORECASE)
_CITY = re.compile(r"^(?:мой город|я живу в(?: городе)?)\s+(.+)$", re.IGNORECASE)
_NOTE = re.compile(r"^запомни[:,]?\s*(?:что\s+)?(.+)$", re.IGNORECASE)

_SHOW = {"что ты обо мне знаешь", "что ты знаешь обо мне", "что ты помнишь обо мне"}
_FORGET = {"забудь обо мне", "забудь всё обо мне", "забудь все обо мне"}


def _prepare(text: str) -> str:
    prepared = text.strip()
    if prepared.lower().startswith("алиса"):
        prepared = prepared[len("алиса"):].lstrip(" ,")
    return prepared


def _clean_value(raw: str) -> str:
    return raw.strip().strip(" \t.,!?;:\"'").strip()


def parse_fact_command(text: str) -> FactCommand | None:
    prepared = _prepare(text)
    if not prepared:
        return None

    match = _NAME.match(prepared)
    if match:
        return FactCommand(FactKind.NAME, _clean_value(match.group(1)))

    match = _CITY.match(prepared)
    if match:
        return FactCommand(FactKind.CITY, _clean_value(match.group(1)))

    lowered = prepared.strip(" \t.,!?;:").lower()
    if lowered in _SHOW:
        return FactCommand(FactKind.SHOW)
    if lowered in _FORGET:
        return FactCommand(FactKind.FORGET)

    match = _NOTE.match(prepared)
    if match:
        value = _clean_value(match.group(1))
        if value:
            return FactCommand(FactKind.NOTE, value)

    return None


def style_hint(style: str | None) -> str:
    if not style:
        return ""
    return _STYLE_HINTS.get(style, "")


def format_facts_prompt(facts: dict[str, str]) -> str:
    items = [(key, value) for key, value in facts.items() if key != "style"]
    if not items:
        return ""
    parts = [f"{_LABELS.get(key, key)} — {value}" for key, value in items]
    return "Известно о пользователе: " + "; ".join(parts) + "."


def facts_reply(facts: dict[str, str]) -> str:
    if not facts:
        return NO_FACTS_TEXT
    parts = [f"{_LABELS.get(key, key)}: {value}" for key, value in facts.items()]
    return FACTS_HEADER + " " + "; ".join(parts) + "."
