"""Session cookie semantics: issue, validate, idle expiry, revoke (T021 / FR-007, FR-008)."""

from __future__ import annotations

import pytest

from app.auth import repo, sessions
from app.db.pool import Pool


@pytest.fixture
async def account(db_pool: Pool) -> repo.AccountRow:
    return await repo.create_account(
        db_pool, email="s1@local", display_name="S1", role="merchant", status="active"
    )


async def test_issue_persists_a_live_row_and_mints_a_valid_cookie(
    db_pool: Pool, account: repo.AccountRow
) -> None:
    token, claims = await sessions.issue(
        db_pool, account_id=account.id, role=account.role, ip="10.0.0.1", user_agent="pytest/1"
    )
    assert claims.account_id == account.id
    assert claims.role == account.role
    read_claims, row = await sessions.current_session(db_pool, token)
    assert read_claims.jti == claims.jti
    assert row.revoked_at is None


async def test_revoke_blocks_the_next_check(db_pool: Pool, account: repo.AccountRow) -> None:
    token, claims = await sessions.issue(
        db_pool, account_id=account.id, role=account.role, ip="10.0.0.2", user_agent="pytest/1"
    )
    await sessions.revoke(db_pool, claims.jti)
    with pytest.raises(sessions.SessionError, match="revoked"):
        await sessions.current_session(db_pool, token)


async def test_revoke_all_can_keep_the_current_session(
    db_pool: Pool, account: repo.AccountRow
) -> None:
    t1, c1 = await sessions.issue(
        db_pool, account_id=account.id, role=account.role, ip="10.0.0.3", user_agent="pytest/1"
    )
    t2, c2 = await sessions.issue(
        db_pool, account_id=account.id, role=account.role, ip="10.0.0.3", user_agent="pytest/2"
    )
    revoked = await sessions.revoke_all(db_pool, account.id, except_jti=c2.jti)
    assert revoked == 1  # only t1
    with pytest.raises(sessions.SessionError):
        await sessions.current_session(db_pool, t1)
    read, _ = await sessions.current_session(db_pool, t2)
    assert read.jti == c2.jti


async def test_idle_timeout_kills_the_session(db_pool: Pool, account: repo.AccountRow) -> None:
    token, claims = await sessions.issue(
        db_pool, account_id=account.id, role=account.role, ip="10.0.0.4", user_agent="pytest/1"
    )
    async with db_pool.connection() as conn:
        await conn.execute(
            "UPDATE auth_sessions SET last_seen_at = now() - interval '1 hour' WHERE jti = %s",
            (claims.jti,),
        )
    with pytest.raises(sessions.SessionError, match="idle"):
        await sessions.current_session(db_pool, token)


async def test_tampered_cookie_is_rejected(db_pool: Pool, account: repo.AccountRow) -> None:
    token, _ = await sessions.issue(
        db_pool, account_id=account.id, role=account.role, ip="10.0.0.5", user_agent="pytest/1"
    )
    tampered = token[:-4] + ("AAAA" if token[-4:] != "AAAA" else "BBBB")
    with pytest.raises(sessions.SessionError):
        await sessions.current_session(db_pool, tampered)


def test_cookie_attributes_are_hardened() -> None:
    attrs = sessions.cookie_attributes(secure=True)
    assert attrs["httponly"] is True
    assert attrs["samesite"] == "Lax"
    assert attrs["secure"] is True
    assert attrs["max_age"] == sessions.ABSOLUTE_LIMIT_SECONDS
