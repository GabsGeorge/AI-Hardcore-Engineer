"""CSRF double-submit (T022 / FR-008)."""

from __future__ import annotations

from app.auth import csrf


def test_new_token_is_long_enough_and_random() -> None:
    a = csrf.new_token()
    b = csrf.new_token()
    assert a != b
    assert len(a) >= 32  # 32 random bytes in base64url is ≥ 43 chars


def test_verify_requires_both_values_and_a_match() -> None:
    token = csrf.new_token()
    assert csrf.verify(token, token) is True
    assert csrf.verify(token, "wrong") is False
    assert csrf.verify(None, token) is False
    assert csrf.verify(token, None) is False
    assert csrf.verify("", "") is False
