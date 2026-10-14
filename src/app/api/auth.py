"""JWT authentication. The effective user is the token's `sub`, nothing else (constitution I)."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

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


async def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
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
