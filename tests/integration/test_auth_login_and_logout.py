"""Login, logout e revogação com cookies HttpOnly + CSRF (T039 / FR-007, FR-008)."""

from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from app.auth import one_time_tokens, passwords, repo
from app.core.config import get_settings
from app.db.pool import Pool


@pytest.fixture(autouse=True)
def _secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    s = get_settings()
    monkeypatch.setattr(s, "session_secret", SecretStr("x" * 64))
    monkeypatch.setattr(s, "password_pepper", SecretStr("pepper-" * 4))


async def _active_account(db_pool: Pool) -> repo.AccountRow:
    account = await repo.create_account(
        db_pool, email="ok@loja.example", display_name="Loja OK", role="merchant", status="active"
    )
    await repo.set_password(db_pool, account.id, passwords.hash_password("senha-segura-demo"))
    return account


async def test_login_sets_hardened_cookies_and_logout_revokes(
    client: httpx.AsyncClient, db_pool: Pool
) -> None:
    await _active_account(db_pool)
    login = await client.post(
        "/v1/auth/login",
        json={"email": "ok@loja.example", "password": "senha-segura-demo"},
    )
    assert login.status_code == 200
    cookies = login.headers.get_list("set-cookie")
    session_cookie = next(c for c in cookies if c.startswith("session="))
    csrf_cookie = next(c for c in cookies if c.startswith("csrf="))
    cookie_lower = session_cookie.lower()
    assert "httponly" in cookie_lower
    assert "samesite=lax" in cookie_lower
    assert "max-age=43200" in cookie_lower
    assert "httponly" not in csrf_cookie.lower()  # the SPA JS needs to read csrf
    body = login.json()
    assert body["account"]["role"] == "merchant"

    me = await client.get("/v1/auth/me")
    assert me.status_code == 200
    csrf_value = client.cookies["csrf"]
    logout = await client.post("/v1/auth/logout", headers={"X-CSRF-Token": csrf_value})
    assert logout.status_code == 204
    second_me = await client.get("/v1/auth/me")
    assert second_me.status_code == 401


async def test_logout_without_csrf_is_rejected(client: httpx.AsyncClient, db_pool: Pool) -> None:
    await _active_account(db_pool)
    await client.post(
        "/v1/auth/login",
        json={"email": "ok@loja.example", "password": "senha-segura-demo"},
    )
    without_header = await client.post("/v1/auth/logout")
    assert without_header.status_code == 403
    assert without_header.json()["error"]["code"] == "csrf_failed"


async def test_reset_password_revokes_every_live_session(
    client: httpx.AsyncClient, db_pool: Pool
) -> None:
    account = await _active_account(db_pool)
    await client.post(
        "/v1/auth/login",
        json={"email": "ok@loja.example", "password": "senha-segura-demo"},
    )
    me1 = await client.get("/v1/auth/me")
    assert me1.status_code == 200

    token = await one_time_tokens.mint(db_pool, account_id=account.id, purpose="password_reset")
    reset = await client.post(
        "/v1/auth/password/reset",
        json={"token": token, "new_password": "outra-senha-segura-123"},
    )
    assert reset.status_code == 200

    me2 = await client.get("/v1/auth/me")
    assert me2.status_code == 401


async def test_login_with_wrong_password_locks_after_five_attempts(
    client: httpx.AsyncClient, db_pool: Pool
) -> None:
    await _active_account(db_pool)
    for _ in range(5):
        resp = await client.post(
            "/v1/auth/login",
            json={"email": "ok@loja.example", "password": "errada-errada-123"},
        )
        assert resp.status_code == 401
    locked = await client.post(
        "/v1/auth/login",
        json={"email": "ok@loja.example", "password": "senha-segura-demo"},
    )
    assert locked.status_code == 423
    assert locked.headers.get("retry-after")
