from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_MONTHS = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)


def datetime_note(tz_name: str | None, now: datetime | None = None) -> str:
    if now is None:
        now = datetime.now(UTC)
    name = (tz_name or "").strip() or "UTC"
    try:
        tz = ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo("UTC")
        name = "UTC"
    local = now.astimezone(tz)
    return (
        f"Сейчас {local.day} {_MONTHS[local.month - 1]} {local.year} года, "
        f"{local:%H:%M} ({name})."
    )
