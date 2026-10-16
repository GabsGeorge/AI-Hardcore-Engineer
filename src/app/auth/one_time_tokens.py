"""Opaque one-time tokens for verify_email, password_reset and invite.

The URL carries the token in clear; the DB only stores ``sha256(token)``. ``consume`` is
single-use (``used_at`` is set in the same transaction that performs the action), so a leaked
link only works once."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Literal

from app.db.pool import Pool

Purpose = Literal["verify_email", "password_reset", "invite"]

VERIFY_LIFETIME = timedelta(hours=24)
RESET_LIFETIME = timedelta(hours=1)
INVITE_LIFETIME = timedelta(hours=24)
TOKEN_BYTES = 32


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _lifetime(purpose: Purpose) -> timedelta:
    return {
        "verify_email": VERIFY_LIFETIME,
        "password_reset": RESET_LIFETIME,
        "invite": INVITE_LIFETIME,
    }[purpose]


async def mint(pool: Pool, *, account_id: str, purpose: Purpose) -> str:
    token = secrets.token_urlsafe(TOKEN_BYTES)
    async with pool.connection() as conn:
        await conn.execute(
            "INSERT INTO auth_one_time_tokens (hash, account_id, purpose, expires_at)"
            " VALUES (%s, %s, %s, now() + %s)",
            (_hash(token), account_id, purpose, _lifetime(purpose)),
        )
    return token


async def consume(pool: Pool, *, token: str, purpose: Purpose) -> str | None:
    """Returns the ``account_id`` and marks the token as used. ``None`` when the token is
    unknown, expired or already used."""
    async with pool.connection() as conn, conn.transaction():
        row = await (
            await conn.execute(
                "UPDATE auth_one_time_tokens SET used_at = now()"
                " WHERE hash = %s AND purpose = %s AND used_at IS NULL AND expires_at > now()"
                " RETURNING account_id",
                (_hash(token), purpose),
            )
        ).fetchone()
    return row["account_id"] if row else None


async def purge_expired(pool: Pool) -> int:
    """Called by the scheduler (feature 001 extended) to drop stale rows after seven days."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "DELETE FROM auth_one_time_tokens"
            " WHERE used_at IS NOT NULL OR expires_at < now() - interval '7 days'"
        )
    return cur.rowcount or 0


def valid_until(now: datetime, purpose: Purpose) -> datetime:
    return now + _lifetime(purpose)
