"""Login rate limiting in Redis (T024 / FR-005)."""

from __future__ import annotations

import pytest
from redis.asyncio import Redis

from app.auth import login_rate


@pytest.fixture
async def redis_client() -> Redis:
    from app.core.config import get_settings

    client = Redis.from_url(get_settings().redis_url)
    await client.flushdb()
    return client


async def test_fifth_account_failure_locks(redis_client: Redis) -> None:
    for _ in range(4):
        decision = await login_rate.on_failure(redis_client, email_lower="t@local", ip="10.0.0.1")
        assert decision.decision == "allow"
    final = await login_rate.on_failure(redis_client, email_lower="t@local", ip="10.0.0.1")
    assert final.decision == "locked"
    check = await login_rate.before_login(redis_client, email_lower="t@local", ip="10.0.0.1")
    assert check.decision == "locked"
    assert check.retry_after_s > 0


async def test_ip_limit_fires_before_account_limit_with_distributed_targets(
    redis_client: Redis,
) -> None:
    for i in range(20):
        decision = await login_rate.on_failure(
            redis_client, email_lower=f"u{i}@local", ip="10.0.0.2"
        )
        if i < 19:
            assert decision.decision == "allow"
    final = await login_rate.on_failure(redis_client, email_lower="u99@local", ip="10.0.0.2")
    assert final.decision == "rate_limited"


async def test_success_clears_both_counters(redis_client: Redis) -> None:
    for _ in range(3):
        await login_rate.on_failure(redis_client, email_lower="t@local", ip="10.0.0.3")
    await login_rate.on_success(redis_client, email_lower="t@local", ip="10.0.0.3")
    check = await login_rate.before_login(redis_client, email_lower="t@local", ip="10.0.0.3")
    assert check.decision == "allow"
