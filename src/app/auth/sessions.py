"""Session cookie: JWT HS256 signed with ``SESSION_SECRET``, with a server-side ``jti`` row so
every session is revocable (sign-out, password change, deactivation, account deletion).

The cookie is ``HttpOnly``, ``SameSite=Lax`` and ``Secure`` outside local dev. ``Max-Age`` is
the absolute cap (12 h); 30 min of inactivity ends the session via ``last_seen_at``.

Nothing in this module talks to FastAPI directly. The /v1/auth endpoints call ``issue`` after a
successful login and attach the cookie; the request pipeline validates with ``current_session``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import jwt
from ulid import ULID

from app.core.config import get_settings
from app.db.pool import Pool

COOKIE_NAME = "session"
CSRF_COOKIE_NAME = "csrf"
ALGO = "HS256"
IDLE_LIMIT_SECONDS = 30 * 60
ABSOLUTE_LIMIT_SECONDS = 12 * 3600


@dataclass(frozen=True)
class SessionClaims:
    account_id: str
    role: str
    jti: str
    issued_at: int


@dataclass(frozen=True)
class SessionRow:
    jti: str
    account_id: str
    issued_at: datetime
    last_seen_at: datetime
    revoked_at: datetime | None
    ip: str
    user_agent: str


class SessionError(Exception):
    """Any failure that must result in an invalidated session (401)."""


def _secret() -> bytes:
    settings = get_settings()
    secret = settings.session_secret
    if secret is None:
        raise RuntimeError("SESSION_SECRET is not configured")
    raw = secret.get_secret_value().encode("utf-8")
    if len(raw) < 32:
        raise RuntimeError("SESSION_SECRET must have at least 32 bytes")
    return raw


def _encode(claims: SessionClaims) -> str:
    now = claims.issued_at
    payload: dict[str, Any] = {
        "sub": claims.account_id,
        "role": claims.role,
        "jti": claims.jti,
        "iat": now,
        "exp": now + ABSOLUTE_LIMIT_SECONDS,
        "iss": get_settings().jwt_issuer,
        "aud": get_settings().jwt_audience,
    }
    return jwt.encode(payload, _secret(), algorithm=ALGO)


def _decode(token: str) -> SessionClaims:
    try:
        payload = jwt.decode(
            token,
            _secret(),
            algorithms=[ALGO],
            audience=get_settings().jwt_audience,
            issuer=get_settings().jwt_issuer,
            options={"require": ["sub", "role", "jti", "iat", "exp"]},
        )
    except jwt.PyJWTError as exc:
        raise SessionError(str(exc)) from exc
    return SessionClaims(
        account_id=str(payload["sub"]),
        role=str(payload["role"]),
        jti=str(payload["jti"]),
        issued_at=int(payload["iat"]),
    )


async def issue(
    pool: Pool, *, account_id: str, role: str, ip: str, user_agent: str
) -> tuple[str, SessionClaims]:
    """Mint a cookie value and persist the row that lets us revoke it later."""
    jti = str(ULID())
    now = int(time.time())
    claims = SessionClaims(account_id=account_id, role=role, jti=jti, issued_at=now)
    async with pool.connection() as conn:
        await conn.execute(
            "INSERT INTO auth_sessions (jti, account_id, ip, user_agent) VALUES (%s, %s, %s, %s)",
            (jti, account_id, ip, user_agent[:200]),
        )
    return _encode(claims), claims


async def current_session(pool: Pool, cookie_value: str) -> tuple[SessionClaims, SessionRow]:
    """Validate the cookie, confirm the row is live, and bump ``last_seen_at``.

    Returns the claims plus the row so handlers can check ``revoked_at`` / idle expiry without a
    second lookup. Raises ``SessionError`` on any trust failure; the caller maps that to 401 and
    clears the cookie.
    """
    claims = _decode(cookie_value)
    async with pool.connection() as conn:
        row = await (
            await conn.execute(
                "SELECT jti, account_id, issued_at, last_seen_at, revoked_at, ip, user_agent"
                " FROM auth_sessions WHERE jti = %s FOR UPDATE",
                (claims.jti,),
            )
        ).fetchone()
        if row is None or row["revoked_at"] is not None:
            raise SessionError("revoked")
        if row["account_id"] != claims.account_id:
            raise SessionError("account_mismatch")
        # Idle expiry: the UPDATE only matches rows still within the window; the RETURNING
        # tells us whether we bumped. No row returned means the session was idle too long.
        bumped = await (
            await conn.execute(
                "UPDATE auth_sessions SET last_seen_at = now()"
                " WHERE jti = %s AND last_seen_at > now() - make_interval(secs => %s)"
                " RETURNING last_seen_at",
                (claims.jti, IDLE_LIMIT_SECONDS),
            )
        ).fetchone()
    if bumped is None:
        raise SessionError("idle")
    return claims, SessionRow(
        jti=row["jti"],
        account_id=row["account_id"],
        issued_at=row["issued_at"],
        last_seen_at=bumped["last_seen_at"],
        revoked_at=row["revoked_at"],
        ip=row["ip"],
        user_agent=row["user_agent"],
    )


async def revoke(pool: Pool, jti: str) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE auth_sessions SET revoked_at = now() WHERE jti = %s AND revoked_at IS NULL",
            (jti,),
        )


async def revoke_all(pool: Pool, account_id: str, *, except_jti: str | None = None) -> int:
    """Used by password reset, account exclusion and admin deactivation."""
    async with pool.connection() as conn:
        if except_jti is None:
            cur = await conn.execute(
                "UPDATE auth_sessions SET revoked_at = now()"
                " WHERE account_id = %s AND revoked_at IS NULL",
                (account_id,),
            )
        else:
            cur = await conn.execute(
                "UPDATE auth_sessions SET revoked_at = now()"
                " WHERE account_id = %s AND revoked_at IS NULL AND jti <> %s",
                (account_id, except_jti),
            )
    return cur.rowcount or 0


def cookie_attributes(*, secure: bool, max_age: int = ABSOLUTE_LIMIT_SECONDS) -> dict[str, Any]:
    """Reused by the Set-Cookie builder for both ``session`` and ``csrf`` cookies.

    ``secure=False`` is for local dev over http://localhost; it stays ``True`` elsewhere.
    """
    return {
        "httponly": True,
        "secure": secure,
        "samesite": "Lax",
        "path": "/",
        "max_age": max_age,
    }
