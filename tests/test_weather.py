import httpx
import pytest
import respx

from app.weather import (
    FORECAST_URL,
    GEOCODING_URL,
    Weather,
    WeatherClient,
    format_weather,
    is_weather_query,
    parse_weather_query,
    weather_code_description,
)


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (0, "ясно"),
        (2, "переменная облачность"),
        (3, "облачно"),
        (45, "туман"),
        (61, "дождь"),
        (71, "снег"),
        (95, "гроза"),
        (999, "облачно"),
    ],
)
def test_weather_code_description(code, expected):
    assert weather_code_description(code) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("погода", ""),
        ("какая сегодня погода", ""),
        ("погода в Екатеринбурге", "екатеринбурге"),
        ("погода в Екатеринбурге?", "екатеринбурге"),
        ("погода Екатеринбург", "екатеринбург"),
        ("какая погода в Москве сегодня", "москве"),
        ("Алиса, погода в Казани", "казани"),
        ("расскажи анекдот", None),
    ],
)
def test_parse_weather_query(text, expected):
    assert parse_weather_query(text) == expected


def test_is_weather_query():
    assert is_weather_query("погода в Москве")
    assert is_weather_query("какая сегодня погода")
    assert not is_weather_query("расскажи анекдот")


def test_format_weather_full():
    weather = Weather(
        city="Екатеринбург",
        temperature=12.4,
        description="облачно",
        wind_speed=3.2,
        t_min=8.1,
        t_max=15.3,
    )
    assert format_weather(weather) == (
        "Сейчас в городе Екатеринбург 12 градусов, облачно, ветер 3 метра в секунду. "
        "Сегодня от 8 до 15 градусов."
    )


def test_format_weather_negative_and_singular_wind():
    weather = Weather(
        city="Норильск",
        temperature=-5.0,
        description="снег",
        wind_speed=1.0,
        t_min=-8.0,
        t_max=-3.0,
    )
    assert format_weather(weather) == (
        "Сейчас в городе Норильск минус 5 градусов, снег, ветер 1 метр в секунду. "
        "Сегодня от минус 8 до минус 3 градусов."
    )


def test_format_weather_without_daily():
    weather = Weather(city="Сочи", temperature=20, description="ясно", wind_speed=2.0)
    assert (
        format_weather(weather)
        == "Сейчас в городе Сочи 20 градусов, ясно, ветер 2 метра в секунду."
    )


@respx.mock
async def test_weather_client_returns_weather():
    respx.get(GEOCODING_URL).mock(
        return_value=httpx.Response(
            200, json={"results": [{"name": "Москва", "latitude": 55.75, "longitude": 37.62}]}
        )
    )
    respx.get(FORECAST_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "current": {
                    "temperature_2m": 5.0,
                    "weather_code": 61,
                    "wind_speed_10m": 2.0,
                },
                "daily": {"temperature_2m_max": [7.0], "temperature_2m_min": [1.0]},
            },
        )
    )
    async with httpx.AsyncClient() as client:
        weather = await WeatherClient(client=client).get("Москва")

    assert weather.city == "Москва"
    assert weather.temperature == 5.0
    assert weather.description == "дождь"
    assert weather.t_max == 7.0


@respx.mock
async def test_weather_client_returns_none_for_unknown_city():
    respx.get(GEOCODING_URL).mock(return_value=httpx.Response(200, json={}))
    async with httpx.AsyncClient() as client:
        assert await WeatherClient(client=client).get("Атлантида") is None
