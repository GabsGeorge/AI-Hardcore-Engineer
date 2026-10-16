"""Parameterised SQL for the auth_* tables and the merchants ↔ account linkage.

Every helper returns primitive dicts or dataclasses so other modules do not depend on psycopg
types. The exclusion of a user's account (FR-016a) runs ``delete_account_cascade``, which is a
single transaction: revoke sessions → remove the LangGraph checkpoints → delete conversations
and feedback by the matching ``users.id`` → unlink from merchants → pseudonymise audit events
→ drop the ``auth_accounts`` row (CASCADE in ``auth_credentials``, ``auth_sessions`` and
``auth_one_time_tokens``).
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from ulid import ULID

from app.core.config import get_settings
from app.db.pool import Pool

AccountStatus = Literal["pending", "active", "locked", "deactivated"]
AccountRole = Literal["merchant", "operator", "admin"]
TokenPurpose = Literal["verify_email", "password_reset", "invite"]


@dataclass(frozen=True)
class AccountRow:
    id: str
    email_lower: str
    display_name: str
    role: AccountRole
    status: AccountStatus
    locked_until: datetime | None
    email_verified_at: datetime | None
    created_at: datetime


def new_account_id() -> str:
    return f"acc_{ULID()}"


def _normalise_email(email: str) -> str:
    return email.strip().lower()


def _row_to_account(row: dict[str, Any]) -> AccountRow:
    return AccountRow(
        id=row["id"],
        email_lower=row["email_lower"],
        display_name=row["display_name"],
        role=row["role"],
        status=row["status"],
        locked_until=row["locked_until"],
        email_verified_at=row["email_verified_at"],
        created_at=row["created_at"],
    )


async def create_account(
    pool: Pool,
    *,
    email: str,
    display_name: str,
    role: AccountRole,
    status: AccountStatus = "pending",
) -> AccountRow:
    """Insert the account only; the credential is written separately so the invite path can
    create an account without a password until the invitee sets one."""
    account_id = new_account_id()
    async with pool.connection() as conn:
        row = await (
            await conn.execute(
                "INSERT INTO auth_accounts (id, email_lower, display_name, role, status)"
                " VALUES (%s, %s, %s, %s, %s)"
                " RETURNING id, email_lower, display_name, role, status,"
                " locked_until, email_verified_at, created_at",
                (account_id, _normalise_email(email), display_name.strip(), role, status),
            )
        ).fetchone()
    # psycopg returns the row we just inserted — None would be a driver bug.
    if row is None:  # pragma: no cover
        raise RuntimeError("INSERT ... RETURNING produced no row")
    return _row_to_account(row)


async def get_account_by_email(pool: Pool, email: str) -> AccountRow | None:
    async with pool.connection() as conn:
        row = await (
            await conn.execute(
                "SELECT id, email_lower, display_name, role, status, locked_until,"
                " email_verified_at, created_at FROM auth_accounts WHERE email_lower = %s",
                (_normalise_email(email),),
            )
        ).fetchone()
    return _row_to_account(row) if row else None


async def get_account_by_id(pool: Pool, account_id: str) -> AccountRow | None:
    async with pool.connection() as conn:
        row = await (
            await conn.execute(
                "SELECT id, email_lower, display_name, role, status, locked_until,"
                " email_verified_at, created_at FROM auth_accounts WHERE id = %s",
                (account_id,),
            )
        ).fetchone()
    return _row_to_account(row) if row else None


async def set_password(pool: Pool, account_id: str, hashed: str) -> None:
    """Create or rotate the password credential and bump ``rotated_at``."""
    async with pool.connection() as conn:
        await conn.execute(
            "INSERT INTO auth_credentials (account_id, kind, secret) VALUES (%s, 'password', %s)"
            " ON CONFLICT (account_id, kind)"
            " DO UPDATE SET secret = EXCLUDED.secret, rotated_at = now()",
            (account_id, hashed),
        )


async def get_password_hash(pool: Pool, account_id: str) -> str | None:
    async with pool.connection() as conn:
        row = await (
            await conn.execute(
                "SELECT secret FROM auth_credentials WHERE account_id = %s AND kind = 'password'",
                (account_id,),
            )
        ).fetchone()
    return row["secret"] if row else None


async def activate_account(pool: Pool, account_id: str) -> None:
    """``pending → active`` when e-mail is verified or an invitee sets the first password."""
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE auth_accounts SET status = 'active', email_verified_at ="
            " COALESCE(email_verified_at, now()) WHERE id = %s AND status <> 'deactivated'",
            (account_id,),
        )


async def set_status(pool: Pool, account_id: str, status: AccountStatus) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE auth_accounts SET status = %s WHERE id = %s",
            (status, account_id),
        )


async def set_locked_until(pool: Pool, account_id: str, when: datetime | None) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE auth_accounts SET locked_until = %s,"
            " status = CASE WHEN %s IS NULL THEN 'active' ELSE 'locked' END"
            " WHERE id = %s AND status <> 'deactivated'",
            (when, when, account_id),
        )


async def record_login_attempt(pool: Pool, *, email: str, ip: str, outcome: str) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            "INSERT INTO auth_login_attempts (email_lower, ip, outcome) VALUES (%s, %s, %s)",
            (_normalise_email(email), ip, outcome),
        )


async def link_merchant(pool: Pool, *, merchant_user_id: str, account_id: str) -> bool:
    """``True`` on link; ``False`` when the merchant is already attached to another account.

    The unique constraint on ``merchants.account_id`` is what makes this safe (FR-021).
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            "UPDATE merchants SET account_id = %s"
            " WHERE user_id = %s AND (account_id IS NULL OR account_id = %s)",
            (account_id, merchant_user_id, account_id),
        )
    return (cur.rowcount or 0) > 0


async def unlink_merchant(pool: Pool, merchant_user_id: str) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE merchants SET account_id = NULL WHERE user_id = %s",
            (merchant_user_id,),
        )


async def merchant_user_id_for(pool: Pool, account_id: str) -> str | None:
    """The ``users.id`` that the graph (001) uses for this account, when linked."""
    async with pool.connection() as conn:
        row = await (
            await conn.execute("SELECT user_id FROM merchants WHERE account_id = %s", (account_id,))
        ).fetchone()
    return row["user_id"] if row else None


def _pseudonym(account_id: str) -> str:
    secret = get_settings().session_secret
    if secret is None:
        raise RuntimeError("SESSION_SECRET must be configured to pseudonymise audit rows")
    key = secret.get_secret_value().encode("utf-8")
    tag = hmac.new(key, account_id.encode("utf-8"), hashlib.sha256).hexdigest()[:16]
    return f"deleted:{tag}"


async def delete_account_cascade(pool: Pool, *, account_id: str, graph: Any) -> dict[str, int]:
    """FR-016a: single transaction wipes conversations, checkpoints, feedback, link and the
    account; audit stays, pseudonymised. The ``users`` row is **not** touched: the lojista's
    chat history under ``users.id`` is removed via the DELETE /v1/me/data path which is
    already LGPD-compliant (feature 001)."""
    pseudonym = _pseudonym(account_id)
    merchant_user_id = await merchant_user_id_for(pool, account_id)
    threads: list[str] = []
    counts: dict[str, int] = {}
    async with pool.connection() as conn, conn.transaction():
        if merchant_user_id is not None:
            rows = await (
                await conn.execute(
                    "SELECT id FROM conversations WHERE user_id = %s", (merchant_user_id,)
                )
            ).fetchall()
            threads = [f"{merchant_user_id}:{row['id']}" for row in rows]
            await conn.execute("DELETE FROM conversations WHERE user_id = %s", (merchant_user_id,))
            await conn.execute("DELETE FROM feedback WHERE user_id = %s", (merchant_user_id,))
            await conn.execute(
                "UPDATE merchants SET account_id = NULL WHERE user_id = %s", (merchant_user_id,)
            )
        counts["conversations"] = len(threads)
        await conn.execute(
            "UPDATE auth_sessions SET revoked_at = now()"
            " WHERE account_id = %s AND revoked_at IS NULL",
            (account_id,),
        )
        await conn.execute(
            "UPDATE audit_events SET actor_id = %s WHERE actor_id = %s",
            (pseudonym, account_id),
        )
        cur = await conn.execute("DELETE FROM auth_accounts WHERE id = %s", (account_id,))
        counts["account"] = cur.rowcount or 0
    # LangGraph checkpoints are keyed by thread_id with no FK; delete them after the DB tx so
    # a partial failure here never leaves the auth tables in a half-state.
    if graph is not None:
        for thread_id in threads:
            await graph.checkpointer.adelete_thread(thread_id)
    counts["pseudonym"] = 1
    return counts
