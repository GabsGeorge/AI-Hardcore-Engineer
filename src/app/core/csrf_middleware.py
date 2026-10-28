"""Global CSRF middleware for cookie-authenticated mutating requests.

Rules:

* Only acts on unsafe methods (POST, PUT, PATCH, DELETE).
* Skips Bearer requests (``Authorization: Bearer ...``): the CLI/API clients do not have a
  cookie origin, so CSRF is not a vector for them.
* Skips requests that do not carry the session cookie: pre-auth flows (register, login,
  password reset, invite accept, email verify) must stay open.
* Otherwise requires ``X-CSRF-Token`` to match the ``csrf`` cookie (double-submit).

Returns a JSON ``csrf_failed`` 403 on failure, matching the per-endpoint shape used before.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from app.auth import csrf as csrf_tokens
from app.auth.sessions import COOKIE_NAME, CSRF_COOKIE_NAME

_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _needs_csrf(request: Request) -> bool:
    if request.method not in _UNSAFE_METHODS:
        return False
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return False
    # Only enforce when the request is actually cookie-authed. Pre-auth endpoints
    # (register, login, password reset, invite accept) have no session cookie yet.
    return bool(request.cookies.get(COOKIE_NAME))


async def enforce_csrf(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    if _needs_csrf(request):
        cookie_value = request.cookies.get(CSRF_COOKIE_NAME)
        header_value = request.headers.get(csrf_tokens.HEADER_NAME)
        if not csrf_tokens.verify(cookie_value, header_value):
            trace_id = getattr(request.state, "trace_id", None)
            return JSONResponse(
                status_code=403,
                content={
                    "error": {"code": "csrf_failed", "message": "Missing or invalid CSRF token."},
                    "trace_id": trace_id,
                },
            )
    return await call_next(request)
