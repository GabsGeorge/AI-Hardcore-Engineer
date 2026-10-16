"""One-time tokens: single use, expiry, hash storage (T023 / FR-002, FR-006)."""

from __future__ import annotations

import asyncio
import hashlib

import pytest

from app.auth import one_time_tokens, repo
from app.db.pool import Pool


@pytest.fixture
async def account(db_pool: Pool) -> repo.AccountRow:
    return await repo.create_account(db_pool, email="t1@local", display_name="T1", role="merchant")


async def test_token_is_stored_as_sha256_hash_only(db_pool: Pool, account: repo.AccountRow) -> None:
    token = await one_time_tokens.mint(db_pool, account_id=account.id, purpose="verify_email")
    async with db_pool.connection() as conn:
        row = await (
            await conn.execute(
                "SELECT hash FROM auth_one_time_tokens WHERE account_id = %s",
                (account.id,),
            )
        ).fetchone()
    assert row is not None
    assert row["hash"] == hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert row["hash"] != token  # raw token is never persisted


async def test_consume_returns_account_once(db_pool: Pool, account: repo.AccountRow) -> None:
    token = await one_time_tokens.mint(db_pool, account_id=account.id, purpose="password_reset")
    first = await one_time_tokens.consume(db_pool, token=token, purpose="password_reset")
    assert first == account.id
    second = await one_time_tokens.consume(db_pool, token=token, purpose="password_reset")
    assert second is None  # already used


async def test_consume_rejects_wrong_purpose(db_pool: Pool, account: repo.AccountRow) -> None:
    token = await one_time_tokens.mint(db_pool, account_id=account.id, purpose="verify_email")
    assert await one_time_tokens.consume(db_pool, token=token, purpose="password_reset") is None


async def test_expired_token_is_rejected(db_pool: Pool, account: repo.AccountRow) -> None:
    token = await one_time_tokens.mint(db_pool, account_id=account.id, purpose="invite")
    async with db_pool.connection() as conn:
        await conn.execute(
            "UPDATE auth_one_time_tokens SET expires_at = now() - interval '1 second'"
            " WHERE account_id = %s",
            (account.id,),
        )
    await asyncio.sleep(0.01)
    assert await one_time_tokens.consume(db_pool, token=token, purpose="invite") is None
