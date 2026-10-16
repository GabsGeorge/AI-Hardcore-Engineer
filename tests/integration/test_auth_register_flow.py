"""Autocadastro: resposta genérica, cria pending e dispara verify (T037 / FR-001, FR-004)."""

from __future__ import annotations

from unittest.mock import patch

import aiosmtplib
import httpx
import pytest
from pydantic import SecretStr

from app.auth import repo as auth_repo
from app.core.config import get_settings
from app.db.pool import Pool


@pytest.fixture(autouse=True)
def _secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    s = get_settings()
    monkeypatch.setattr(s, "session_secret", SecretStr("x" * 64))
    monkeypatch.setattr(s, "password_pepper", SecretStr("pepper-" * 4))


async def test_register_sends_verification_and_creates_pending_account(
    client: httpx.AsyncClient, db_pool: Pool
) -> None:
    sent: list[tuple[str, str]] = []

    async def _fake(message, **_):  # type: ignore[no-untyped-def]
        sent.append((message["To"], message.get_content()))

    with patch.object(aiosmtplib, "send", side_effect=_fake):
        response = await client.post(
            "/v1/auth/register",
            json={
                "display_name": "Loja Demo",
                "email": "demo@loja.example",
                "password": "senha-segura-demo",
            },
        )

    assert response.status_code == 202
    assert response.json() == {"status": "pending"}
    account = await auth_repo.get_account_by_email(db_pool, "demo@loja.example")
    assert account is not None
    assert account.status == "pending"
    assert account.role == "merchant"
    assert sent and sent[0][0] == "demo@loja.example"
    assert "/verify?token=" in sent[0][1]


async def test_duplicate_registration_returns_the_same_response(
    client: httpx.AsyncClient, db_pool: Pool
) -> None:
    """FR-004: a response for an existing e-mail must be indistinguishable from a new one."""
    with patch.object(aiosmtplib, "send"):
        first = await client.post(
            "/v1/auth/register",
            json={
                "display_name": "Loja Demo",
                "email": "dup@loja.example",
                "password": "senha-segura-demo",
            },
        )
    assert first.status_code == 202
    sent_count = 0

    async def _count(message, **_):  # type: ignore[no-untyped-def]
        nonlocal sent_count
        sent_count += 1

    with patch.object(aiosmtplib, "send", side_effect=_count):
        second = await client.post(
            "/v1/auth/register",
            json={
                "display_name": "Loja Outra",
                "email": "dup@loja.example",
                "password": "senha-segura-outra",
            },
        )
    assert second.status_code == 202
    assert second.json() == first.json()
    assert sent_count == 0  # no second e-mail; account exists
    async with db_pool.connection() as conn:
        rows = await (
            await conn.execute(
                "SELECT action FROM audit_events WHERE action LIKE 'account_registered%'"
                " ORDER BY ts"
            )
        ).fetchall()
    actions = [row["action"] for row in rows]
    assert "account_registered" in actions
    assert "account_registered_duplicate" in actions


async def test_weak_password_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/v1/auth/register",
        json={"display_name": "Loja", "email": "x@loja.example", "password": "short"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "weak_password"
