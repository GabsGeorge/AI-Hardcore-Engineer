"""Double-submit CSRF: the ``csrf`` cookie is readable by the SPA JS, and every mutation must
echo it back in ``X-CSRF-Token``. ``SameSite=Lax`` on the session cookie is the first barrier;
this is defense in depth."""

from __future__ import annotations

import hmac
import secrets

TOKEN_BYTES = 32
HEADER_NAME = "X-CSRF-Token"


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def verify(cookie_value: str | None, header_value: str | None) -> bool:
    if not cookie_value or not header_value:
        return False
    # Compare in constant time; both values are plain base64url strings.
    return hmac.compare_digest(cookie_value, header_value)
