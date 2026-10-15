"""Per-user rate limit and Idempotency-Key replay in Redis (REQ-SEC-08, REQ-API-06).

shortcut: fixed 60 s window, a user can burst up to 2x the limit across a minute boundary;
switch to a sliding window if the limit becomes contractual.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from typing import Any

from fastapi import Request
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.errors import AppError

_IDEM_TTL = 24 * 3600
# Longer than any turn, short enough that a crashed request doesn't lock its key for a day.
_IN_FLIGHT_TTL = 120


async def check_rate_limit(request: Request, user_id: str) -> None:
    redis: Redis = request.app.state.redis
    now = time.time()
    key = f"rl:{user_id}:{int(now // 60)}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 65)
    if count > get_settings().rate_limit_per_min:
        retry_after = max(1, math.ceil(60 - now % 60))
        raise AppError(
            429,
            "rate_limited",
            f"Too many requests. Try again in {retry_after}s.",
            headers={"Retry-After": str(retry_after)},
        )


def _hash_body(body: dict[str, Any]) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def idempotency_get_or_claim(
    request: Request, user_id: str, key: str | None, body: dict[str, Any]
) -> dict[str, Any] | None:
    """Cached response on replay; ``None`` means "run it and call idempotency_store"."""
    if key is None:
        return None
    redis: Redis = request.app.state.redis
    rec_key = f"idem:{user_id}:{key}"
    body_hash = _hash_body(body)
    claim = json.dumps({"body_hash": body_hash, "response": None})
    if await redis.set(rec_key, claim, ex=_IN_FLIGHT_TTL, nx=True):
        return None
    raw = await redis.get(rec_key)
    if raw is None:  # the claim expired between our two calls
        return None
    rec = json.loads(raw)
    if rec["body_hash"] != body_hash:
        raise AppError(
            409, "idempotency_conflict", "Idempotency-Key reused with a different payload."
        )
    if rec["response"] is None:
        raise AppError(
            409, "idempotency_in_progress", "A request with this Idempotency-Key is running."
        )
    return dict(rec["response"])


async def idempotency_store(
    request: Request, user_id: str, key: str | None, body: dict[str, Any], response: dict[str, Any]
) -> None:
    if key is None:
        return
    redis: Redis = request.app.state.redis
    rec = {"body_hash": _hash_body(body), "response": response}
    await redis.set(f"idem:{user_id}:{key}", json.dumps(rec), ex=_IDEM_TTL)
