from datetime import UTC, datetime

from app.clock import datetime_note

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


def test_datetime_note_formats_russian_date_in_timezone():
    assert datetime_note("Europe/Moscow", now=NOW) == (
        "Сейчас 28 сентября 2026 года, 15:00 (Europe/Moscow)."
    )


def test_datetime_note_falls_back_to_utc_for_unknown_zone():
    assert datetime_note("Nowhere/Unknown", now=NOW) == (
        "Сейчас 28 сентября 2026 года, 12:00 (UTC)."
    )


def test_datetime_note_handles_empty_timezone():
    assert datetime_note("", now=NOW) == "Сейчас 28 сентября 2026 года, 12:00 (UTC)."


def test_datetime_note_handles_none_timezone():
    assert datetime_note(None, now=NOW) == "Сейчас 28 сентября 2026 года, 12:00 (UTC)."
