import re
from dataclasses import dataclass

import httpx

from app.commands import normalize

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

WEATHER_ASK_CITY = "В каком городе узнать погоду? Назови город."
WEATHER_ERROR = "Не получилось узнать погоду. Попробуй позже."
WEATHER_CITY_NOT_FOUND = "Не нашёл город «{city}». Попробуй назвать иначе."

_CITY_IN = re.compile(r"погод\w*\s+(?:в|во)\s+(.+)$")
_CITY_AFTER = re.compile(r"погод\w*\s+(.+)$")
_LEADING_FILLER = re.compile(r"^(?:в|во|на|за|у)\s+")
_TRAILING_FILLER = re.compile(r"\s+(?:сегодня|сейчас|завтра)$")

_DESCRIPTIONS = {
    0: "ясно",
    1: "малооблачно",
    2: "переменная облачность",
    3: "облачно",
    45: "туман",
    48: "туман",
    51: "морось",
    53: "морось",
    55: "морось",
    56: "ледяная морось",
    57: "ледяная морось",
    61: "дождь",
    63: "дождь",
    65: "сильный дождь",
    66: "ледяной дождь",
    67: "ледяной дождь",
    71: "снег",
    73: "снег",
    75: "сильный снег",
    77: "снежные зёрна",
    80: "ливень",
    81: "ливень",
    82: "сильный ливень",
    85: "снегопад",
    86: "снегопад",
    95: "гроза",
    96: "гроза с градом",
    99: "гроза с градом",
}


@dataclass
class Weather:
    city: str
    temperature: float
    description: str
    wind_speed: float
    t_min: float | None = None
    t_max: float | None = None


def weather_code_description(code: int | None) -> str:
    return _DESCRIPTIONS.get(code, "облачно")


def is_weather_query(text: str) -> bool:
    return "погод" in normalize(text)


def city_from_entities(entities: list | None) -> str | None:
    for entity in entities or []:
        if entity.get("type") == "YANDEX.GEO":
            value = entity.get("value") or {}
            city = value.get("city")
            if city:
                return city
    return None


def parse_weather_query(text: str) -> str | None:
    normalized = normalize(text)
    if "погод" not in normalized:
        return None
    match = _CITY_IN.search(normalized)
    if match:
        return _TRAILING_FILLER.sub("", match.group(1)).strip()
    match = _CITY_AFTER.search(normalized)
    if match:
        tail = _LEADING_FILLER.sub("", match.group(1).strip())
        tail = _TRAILING_FILLER.sub("", tail).strip()
        if tail and tail not in {"в", "во", "на", "сегодня", "сейчас", "завтра"}:
            return tail
    return ""


def _temp_word(value: float) -> str:
    rounded = round(value)
    if rounded < 0:
        return f"минус {abs(rounded)}"
    return str(rounded)


def _wind_unit(value: float) -> str:
    rounded = round(value)
    if rounded % 10 == 1 and rounded % 100 != 11:
        return "метр"
    if rounded % 10 in (2, 3, 4) and rounded % 100 not in (12, 13, 14):
        return "метра"
    return "метров"


def format_weather(weather: Weather) -> str:
    text = (
        f"Сейчас в городе {weather.city} {_temp_word(weather.temperature)} градусов, "
        f"{weather.description}, ветер {round(weather.wind_speed)} "
        f"{_wind_unit(weather.wind_speed)} в секунду."
    )
    if weather.t_min is not None and weather.t_max is not None:
        text += (
            f" Сегодня от {_temp_word(weather.t_min)} до {_temp_word(weather.t_max)} градусов."
        )
    return text


def _first(values: list | None) -> float | None:
    if not values:
        return None
    return values[0]


class WeatherClient:
    def __init__(self, timeout: float = 4.0, client: httpx.AsyncClient | None = None):
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def get(self, city: str) -> Weather | None:
        geo = await self._client.get(
            GEOCODING_URL,
            params={"name": city, "count": 1, "language": "ru", "format": "json"},
        )
        geo.raise_for_status()
        results = (geo.json() or {}).get("results") or []
        if not results:
            return None
        place = results[0]

        forecast = await self._client.get(
            FORECAST_URL,
            params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": "temperature_2m,weather_code,wind_speed_10m",
                "daily": "temperature_2m_max,temperature_2m_min",
                "timezone": "auto",
                "forecast_days": 1,
                "wind_speed_unit": "ms",
            },
        )
        forecast.raise_for_status()
        data = forecast.json()
        current = data.get("current") or {}
        daily = data.get("daily") or {}

        return Weather(
            city=place.get("name") or city,
            temperature=current.get("temperature_2m", 0),
            description=weather_code_description(current.get("weather_code")),
            wind_speed=current.get("wind_speed_10m", 0),
            t_min=_first(daily.get("temperature_2m_min")),
            t_max=_first(daily.get("temperature_2m_max")),
        )

    async def aclose(self) -> None:
        await self._client.aclose()
