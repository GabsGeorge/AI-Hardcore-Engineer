"""Knowledge tools (contracts/tools.md) over the frozen models of tools/interfaces.py. Both read
only public content. Timeouts (5 s) are enforced by agents.common.call_tool."""

import asyncio
import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

from ddgs import DDGS
from langchain_core.runnables import RunnableConfig
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.observability.logging import get_logger
from app.rag import retriever
from app.tools.interfaces import SearchKnowledgeBaseInput, WebResult, WebSearchInput

MAX_WEB_RESULTS = 5
VOLATILE_TTL = 15 * 60  # exchange rates, weather: stale quickly
DEFAULT_TTL = 6 * 3600
_VOLATILE = re.compile(
    r"c[aâ]mbio|cota[cç][aã]o|d[oó]lar|dollar|euro|exchange|currency|clima|tempo|temperatura"
    r"|previs[aã]o|chuva|weather|forecast|temperature|rain",
    re.I,
)


async def search_knowledge_base(
    args: SearchKnowledgeBaseInput, config: RunnableConfig
) -> list[retriever.KbHit]:
    return await retriever.search(args.query, args.lang)


def ddgs_text(query: str, max_results: int) -> list[dict[str, Any]]:
    """DuckDuckGo text search. Blocking: runs in a worker thread. Tests replace it."""
    return list(DDGS().text(query, region="br-pt", max_results=max_results))


def cache_key(query: str) -> str:
    normalized = " ".join(query.lower().split())
    return f"websearch:{hashlib.sha256(normalized.encode()).hexdigest()}"


_redis: Redis | None = None


def _cache() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(get_settings().redis_url)
    return _redis


async def web_search(args: WebSearchInput, config: RunnableConfig) -> list[WebResult]:
    """Up to 5 results with the date they were retrieved; cached in Redis (research R-02). A cache
    failure only costs a fresh search."""
    key = cache_key(args.query)
    try:
        cached = await _cache().get(key)
    except RedisError as exc:
        get_logger().warning("web_cache_unavailable", error=type(exc).__name__)
        cached = None
    if cached:
        return [WebResult.model_validate(r) for r in json.loads(cached)]

    raw = await asyncio.to_thread(ddgs_text, args.query, MAX_WEB_RESULTS)
    now = datetime.now(UTC)
    results = [
        WebResult(
            title=str(r.get("title") or r["href"]),
            url=str(r["href"]),
            snippet=str(r.get("body") or ""),
            retrieved_at=now,
        )
        for r in raw
        if str(r.get("href", "")).startswith(("https://", "http://"))
    ][:MAX_WEB_RESULTS]
    if results:
        ttl = VOLATILE_TTL if _VOLATILE.search(args.query) else DEFAULT_TTL
        payload = json.dumps([r.model_dump(mode="json") for r in results])
        try:
            await _cache().set(key, payload, ex=ttl)
        except RedisError as exc:
            get_logger().warning("web_cache_unavailable", error=type(exc).__name__)
    return results
