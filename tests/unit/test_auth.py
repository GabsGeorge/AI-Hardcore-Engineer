import time

import jwt
import pytest

from app.api.auth import AuthError, create_token, decode_token
from app.core.config import get_settings

pytestmark = pytest.mark.req("REQ-SEC-01")


def _raw(**claims: object) -> str:
    s = get_settings()
    base = {
        "sub": "cliente1988",
        "role": "merchant",
        "iss": s.jwt_issuer,
        "aud": s.jwt_audience,
        "exp": int(time.time()) + 60,
    }
    base.update(claims)
    payload = {k: v for k, v in base.items() if v is not None}
    return jwt.encode(payload, s.jwt_secret.get_secret_value(), algorithm="HS256")


def test_valid_token_round_trip() -> None:
    claims = decode_token(create_token("cliente1988", "merchant"))
    assert (claims["sub"], claims["role"]) == ("cliente1988", "merchant")


@pytest.mark.parametrize(
    "token",
    [
        "not-a-jwt",
        _raw(exp=int(time.time()) - 10),
        _raw(aud="other-api"),
        _raw(iss="someone-else"),
        _raw(sub=None),
        _raw(role=None),
    ],
)
def test_invalid_tokens_are_rejected(token: str) -> None:
    with pytest.raises(AuthError):
        decode_token(token)


def test_token_signed_with_other_key_is_rejected() -> None:
    s = get_settings()
    forged = jwt.encode(
        {
            "sub": "cliente1988",
            "role": "merchant",
            "iss": s.jwt_issuer,
            "aud": s.jwt_audience,
            "exp": int(time.time()) + 60,
        },
        "x" * 64,
        algorithm="HS256",
    )
    with pytest.raises(AuthError):
        decode_token(forged)


def test_alg_none_is_rejected() -> None:
    unsigned = jwt.encode({"sub": "cliente1988", "role": "merchant"}, key=None, algorithm="none")
    with pytest.raises(AuthError):
        decode_token(unsigned)
