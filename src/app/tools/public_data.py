"""Real-time public data for the two general questions the challenge names: weather and exchange
rate. DuckDuckGo answers them with generic pages (no temperature, no rate), so the model has
nothing to ground a reply on and rightly says it does not know. Open-Meteo and AwesomeAPI return the
figures themselves; both are free and need no key.

Every failure (no match, no city, timeout, bad payload) returns ``None`` and `web_search` falls back
to DuckDuckGo. Nothing here invents a value: a figure is either read from the API or absent.
"""

import re
from datetime import UTC, datetime
from typing import Any

import httpx

from app.tools.interfaces import WebResult

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FX_URL = "https://economia.awesomeapi.com.br/json/last/{code}-BRL"
FX_DOCS_URL = "https://docs.awesomeapi.com.br/api-de-moedas"
TIMEOUT = 2.0

_WEATHER = re.compile(
    r"previs[aã]o do tempo|clima|tempo (?:em|para|na|no)|weather|forecast|temperatura", re.I
)
_CITY = re.compile(
    r"\b(?:em|in|para|for|na|no)\s+(.+?)"
    r"(?:\s+(?:amanh[ãa]|hoje|agora|tomorrow|today|now)\b|[?.!,]|$)",
    re.I,
)
_TOMORROW = re.compile(r"amanh[ãa]|tomorrow", re.I)
_CURRENCIES = {
    "euro": "EUR",
    "dólar": "USD",
    "dolar": "USD",
    "dollar": "USD",
    "libra": "GBP",
    "pound": "GBP",
}
_CURRENCY = re.compile("|".join(_CURRENCIES), re.I)
_FX_INTENT = re.compile(
    r"cota[cç][aã]o|c[aâ]mbio|exchange|rate|hoje|today|vale|price|pre[cç]o", re.I
)


def _result(title: str, url: str, snippet: str) -> list[WebResult]:
    return [WebResult(title=title, url=url, snippet=snippet, retrieved_at=datetime.now(UTC))]


async def _weather(query: str, client: httpx.AsyncClient) -> list[WebResult] | None:
    if not _WEATHER.search(query):
        return None
    match = _CITY.search(query)
    if match is None:
        return None
    city = match.group(1).strip()
    geo = (
        await client.get(
            GEOCODING_URL, params={"name": city, "count": 1, "language": "pt", "format": "json"}
        )
    ).json()
    places: list[dict[str, Any]] = geo.get("results") or []
    if not places:
        return None
    place = places[0]
    forecast = (
        await client.get(
            FORECAST_URL,
            params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "daily": "temperature_2m_max,temperature_2m_min,"
                "precipitation_probability_max,precipitation_sum",
                "timezone": "auto",
                "forecast_days": 3,
            },
        )
    ).json()
    daily = forecast["daily"]
    day = 1 if _TOMORROW.search(query) else 0
    where = ", ".join(str(p) for p in (place.get("name"), place.get("admin1")) if p)
    # Label the day relative to now: the model sees a bare date and cannot tell it is the
    # "amanhã" the merchant asked about, so it may rightly refuse to vouch for it.
    label = "amanhã" if day == 1 else "hoje"
    snippet = (
        f"{label} ({daily['time'][day]}): máxima {daily['temperature_2m_max'][day]}°C, "
        f"mínima {daily['temperature_2m_min'][day]}°C, "
        f"probabilidade de chuva {daily['precipitation_probability_max'][day]}%, "
        f"precipitação {daily['precipitation_sum'][day]} mm. Fonte: Open-Meteo."
    )
    return _result(f"Previsão do tempo — {where}", "https://open-meteo.com/", snippet)


async def _exchange(query: str, client: httpx.AsyncClient) -> list[WebResult] | None:
    currency = _CURRENCY.search(query)
    if currency is None or not _FX_INTENT.search(query):
        return None
    code = _CURRENCIES[currency.group(0).lower()]
    quote = (await client.get(FX_URL.format(code=code))).json()[f"{code}BRL"]
    snippet = (
        f"{quote['name']}: compra R$ {quote['bid']}, venda R$ {quote['ask']}, "
        f"variação {quote['pctChange']}% (atualizado em {quote['create_date']}). "
        "Fonte: AwesomeAPI."
    )
    return _result(f"Cotação {code}/BRL", FX_DOCS_URL, snippet)


async def lookup(query: str, client: httpx.AsyncClient | None = None) -> list[WebResult] | None:
    """Weather or exchange-rate figures for `query`, or None when it is neither or a call fails."""
    owned = client is None
    http = client or httpx.AsyncClient(timeout=TIMEOUT)
    try:
        return await _weather(query, http) or await _exchange(query, http)
    except Exception:  # noqa: BLE001 — any failure degrades to the generic web search
        return None
    finally:
        if owned:
            await http.aclose()
