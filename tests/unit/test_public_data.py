"""Weather and exchange-rate figures come from the APIs, never from the model. HTTP is replaced by
a MockTransport, so nothing here touches the network."""

import json

import httpx
import pytest

from app.tools import public_data

pytestmark = pytest.mark.req("REQ-KNW-02")

FORECAST = {
    "daily": {
        "time": ["2026-11-16", "2026-11-17", "2026-11-18"],
        "temperature_2m_max": [28.1, 25.4, 24.0],
        "temperature_2m_min": [17.0, 16.2, 15.5],
        "precipitation_probability_max": [10, 65, 30],
        "precipitation_sum": [0.0, 7.4, 1.2],
    }
}
GEOCODING = {
    "results": [
        {
            "name": "Porto Alegre",
            "admin1": "Rio Grande do Sul",
            "latitude": -30.03,
            "longitude": -51.23,
        }
    ]
}
QUOTE = {
    "EURBRL": {
        "name": "Euro/Real Brasileiro",
        "bid": "6.12",
        "ask": "6.13",
        "pctChange": "0.21",
        "create_date": "2026-11-16 10:00:00",
    }
}


def _client(handler: httpx.MockTransport | None = None) -> httpx.AsyncClient:
    def route(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host == "geocoding-api.open-meteo.com":
            return httpx.Response(200, json=GEOCODING)
        if host == "api.open-meteo.com":
            return httpx.Response(200, json=FORECAST)
        if host == "economia.awesomeapi.com.br":
            return httpx.Response(200, json=QUOTE)
        return httpx.Response(404)

    return httpx.AsyncClient(transport=handler or httpx.MockTransport(route))


async def test_weather_for_tomorrow_reads_the_second_forecast_day() -> None:
    async with _client() as client:
        results = await public_data.lookup("Previsão do tempo em Porto Alegre amanhã", client)
    assert results is not None and len(results) == 1
    snippet = results[0].snippet
    assert snippet.startswith("amanhã (2026-11-17)")
    assert "25.4°C" in snippet and "16.2°C" in snippet
    assert "65%" in snippet and "Open-Meteo" in snippet
    assert "Porto Alegre" in results[0].title


async def test_weather_without_a_day_word_reads_today() -> None:
    async with _client() as client:
        results = await public_data.lookup("clima em Porto Alegre", client)
    assert results is not None and results[0].snippet.startswith("hoje (2026-11-16)")


async def test_english_weather_question() -> None:
    async with _client() as client:
        results = await public_data.lookup(
            "What is the weather forecast in Porto Alegre tomorrow?", client
        )
    assert results is not None and "2026-11-17" in results[0].snippet


async def test_exchange_rate_returns_the_quote() -> None:
    async with _client() as client:
        results = await public_data.lookup("Cotação do euro hoje", client)
    assert results is not None and len(results) == 1
    assert "R$ 6.12" in results[0].snippet and "R$ 6.13" in results[0].snippet
    assert results[0].title == "Cotação EUR/BRL"


async def test_unrelated_question_is_not_handled() -> None:
    async with _client() as client:
        assert (
            await public_data.lookup("Como funciona a antecipação de recebíveis?", client) is None
        )


async def test_unknown_city_falls_back() -> None:
    def route(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    async with _client(httpx.MockTransport(route)) as client:
        assert await public_data.lookup("previsão do tempo em Xyzzyville", client) is None


async def test_api_failure_falls_back_instead_of_raising() -> None:
    def route(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    async with _client(httpx.MockTransport(route)) as client:
        assert await public_data.lookup("Cotação do euro hoje", client) is None
        assert await public_data.lookup("previsão do tempo em Porto Alegre", client) is None


async def test_malformed_payload_falls_back() -> None:
    def route(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=json.dumps({"unexpected": True}))

    async with _client(httpx.MockTransport(route)) as client:
        assert await public_data.lookup("Cotação do dólar hoje", client) is None
