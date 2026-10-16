"""Login rate limiting (research §5): per-account lockout and per-IP throttle in Redis.

The DB auth_login_attempts table is for forensic use; the "is this attempt allowed" question is
answered by two Redis counters so the hot path stays fast. Both windows are 15 min fixed; the
``shortcut:`` is documented — a sliding window is an easy upgrade when the limit becomes
contractual.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from redis.asyncio import Redis

ACCOUNT_WINDOW_S = 15 * 60
IP_WINDOW_S = 15 * 60
ACCOUNT_LIMIT = 5
IP_LIMIT = 20

Decision = Literal["allow", "locked", "rate_limited"]


@dataclass(frozen=True)
class RateCheck:
    decision: Decision
    retry_after_s: int = 0


async def _incr(redis: Redis, key: str, window: int) -> int:
    pipe = redis.pipeline(transaction=False)
    pipe.incr(key)
    pipe.expire(key, window)
    count, _ = await pipe.execute()
    return int(count)


async def before_login(redis: Redis, *, email_lower: str, ip: str) -> RateCheck:
    """Checks only — no counter is bumped on allow; the bump happens on failure via
    ``on_failure``. The caller still records the attempt in Postgres."""
    account_key = f"auth:login:acct:{email_lower}"
    ip_key = f"auth:login:ip:{ip}"
    pipe = redis.pipeline(transaction=False)
    pipe.get(account_key)
    pipe.get(ip_key)
    acct_raw, ip_raw = await pipe.execute()
    acct_fails = int(acct_raw) if acct_raw else 0
    ip_fails = int(ip_raw) if ip_raw else 0
    if ip_fails >= IP_LIMIT:
        ttl = int(await redis.ttl(ip_key))
        return RateCheck(decision="rate_limited", retry_after_s=max(ttl, 1))
    if acct_fails >= ACCOUNT_LIMIT:
        ttl = int(await redis.ttl(account_key))
        return RateCheck(decision="locked", retry_after_s=max(ttl, 1))
    return RateCheck(decision="allow")


async def on_failure(redis: Redis, *, email_lower: str, ip: str) -> RateCheck:
    """Bump both counters after a bad credential. If either tripped, the caller returns the
    locked/rate_limited response."""
    account_key = f"auth:login:acct:{email_lower}"
    ip_key = f"auth:login:ip:{ip}"
    acct_fails = await _incr(redis, account_key, ACCOUNT_WINDOW_S)
    ip_fails = await _incr(redis, ip_key, IP_WINDOW_S)
    if ip_fails >= IP_LIMIT:
        return RateCheck(decision="rate_limited", retry_after_s=IP_WINDOW_S)
    if acct_fails >= ACCOUNT_LIMIT:
        return RateCheck(decision="locked", retry_after_s=ACCOUNT_WINDOW_S)
    return RateCheck(decision="allow")


async def on_success(redis: Redis, *, email_lower: str, ip: str) -> None:
    """Reset the per-account counter so one earlier mistake doesn't haunt the user."""
    await redis.delete(f"auth:login:acct:{email_lower}", f"auth:login:ip:{ip}")
