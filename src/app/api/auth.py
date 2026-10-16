"""JWT authentication. The effective user is the token's `sub`, nothing else (constitution I).

Two emitters coexist for the duration of the UI web migration:

- ``Authorization: Bearer <jwt>`` from ``scripts/issue_token.py`` and the 001 seed; still used
  by the API clients and k6; the ``sub`` is the ``users.id`` of the merchant seed.
- A ``session`` cookie minted by ``src/app/auth/sessions.issue`` after a successful login via
  the UI; the ``sub`` is the ``auth_accounts.id`` (``acc_*``), which translates to a seed
  ``users.id`` through ``merchants.account_id`` when the admin has linked the account.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth import repo as auth_repo
from app.auth import sessions as cookie_sessions
from app.core.config import get_settings
from app.core.errors import forbidden, unauthorized
from app.db import repo
from app.db.pool import get_pool

ALGORITHM = "HS256"
ROLES = ("merchant", "operator", "admin")

_bearer = HTTPBearer(auto_error=False)


class AuthError(Exception):
    pass


@dataclass(frozen=True)
class CurrentUser:
    id: str
    role: str


def create_token(sub: str, role: str, ttl_seconds: int = 3600) -> str:
    s = get_settings()
    now = int(time.time())
    claims = {
        "sub": sub,
        "role": role,
        "iss": s.jwt_issuer,
        "aud": s.jwt_audience,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(claims, s.jwt_secret.get_secret_value(), algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    s = get_settings()
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            s.jwt_secret.get_secret_value(),
            algorithms=[ALGORITHM],
            audience=s.jwt_audience,
            issuer=s.jwt_issuer,
            options={"require": ["exp", "sub", "iss", "aud"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthError(str(exc)) from exc
    if claims.get("role") not in ROLES:
        raise AuthError("missing or unknown role")
    return claims


async def _from_cookie(request: Request) -> CurrentUser | None:
    """UI web clients send only a cookie. Return ``None`` to let the Bearer path try next."""
    cookie_value = request.cookies.get(cookie_sessions.COOKIE_NAME)
    if not cookie_value:
        return None
    try:
        claims, _ = await cookie_sessions.current_session(get_pool(), cookie_value)
    except cookie_sessions.SessionError as exc:
        raise unauthorized() from exc
    account = await auth_repo.get_account_by_id(get_pool(), claims.account_id)
    if account is None or account.status != "active" or account.role != claims.role:
        raise unauthorized()
    # Lojistas: traduz acc_* para a users.id ligada ao merchant (quando houver vínculo). O graph
    # da 001 e as tools continuam vendo o identificador do seed, nada muda do ADR 0005.
    user_id: str = account.id
    if account.role == "merchant":
        linked = await auth_repo.merchant_user_id_for(get_pool(), account.id)
        if linked is not None:
            user_id = linked
    return CurrentUser(id=user_id, role=account.role)


async def current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    # Cookie-first: the SPA never carries a Bearer token, so a cookie is tried before falling
    # back to the legacy header. Both are mutually exclusive in practice.
    from_cookie = await _from_cookie(request)
    if from_cookie is not None:
        return from_cookie
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized()
    try:
        claims = decode_token(credentials.credentials)
    except AuthError as exc:
        raise unauthorized() from exc
    user = await repo.get_user(get_pool(), claims["sub"])
    if user is None or user["role"] != claims["role"]:
        raise unauthorized()
    return CurrentUser(id=user["id"], role=user["role"])


def require_role(*roles: str) -> Callable[[CurrentUser], CurrentUser]:
    """Dependency factory: raises 403 forbidden_role when the user's role is not allowed."""

    def _check(user: CurrentUser = Depends(current_user)) -> CurrentUser:
        if user.role not in roles:
            raise forbidden("forbidden_role", "Operator role required.")
        return user

    return _check
