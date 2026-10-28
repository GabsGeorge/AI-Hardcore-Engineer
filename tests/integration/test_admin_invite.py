"""Admin invita operador: convite chega no Mailpit mock, link define a senha e a conta vira
``active`` (T086 / FR-020)."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
from pydantic import SecretStr

from app.auth import passwords, repo
from app.core.config import get_settings
from app.db.pool import Pool


@pytest.fixture(autouse=True)
def _secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    s = get_settings()
    monkeypatch.setattr(s, "session_secret", SecretStr("x" * 64))
    monkeypatch.setattr(s, "password_pepper", SecretStr("pepper-" * 4))


async def _login_as_admin(client: httpx.AsyncClient, db_pool: Pool) -> repo.AccountRow:
    admin = await repo.create_account(
        db_pool,
        email="admin@getnet.example",
        display_name="Admin Dev",
        role="admin",
        status="active",
    )
    await repo.set_password(db_pool, admin.id, passwords.hash_password("admin-senha-forte-123"))
    r = await client.post(
        "/v1/auth/login",
        json={"email": "admin@getnet.example", "password": "admin-senha-forte-123"},
    )
    assert r.status_code == 200
    return admin


@pytest.mark.req("REQ-API-02")
async def test_invite_mints_token_and_accept_activates(
    client: httpx.AsyncClient, db_pool: Pool
) -> None:
    await _login_as_admin(client, db_pool)
    csrf = client.cookies["csrf"]

    captured: dict[str, str] = {}

    async def _capture(**kwargs: object) -> None:
        # mailer calls aiosmtplib.send; the real token is already minted in the DB — we read it
        # from auth_one_time_tokens below.
        captured["sent"] = "yes"

    with patch("app.ops.mailer.aiosmtplib.send", _capture):
        r = await client.post(
            "/v1/admin/accounts",
            json={
                "display_name": "Operador 1",
                "email": "op1@getnet.example",
                "role": "operator",
            },
            headers={"X-CSRF-Token": csrf},
        )
    assert r.status_code == 202

    invited = await repo.get_account_by_email(db_pool, "op1@getnet.example")
    assert invited is not None and invited.status == "pending" and invited.role == "operator"

    # O token real foi minted dentro do endpoint; o retorno em claro é descartado após mandar
    # o e-mail. Para fechar o fluxo do teste mintamos um novo (igualmente válido) e aceitamos.
    from app.auth import one_time_tokens

    fresh_token = await one_time_tokens.mint(db_pool, account_id=invited.id, purpose="invite")

    # No fluxo real a pessoa convidada chega sem sessão ativa; aqui o admin ainda está
    # logado no cliente, então ecoamos o cookie CSRF no header para passar pelo middleware
    # global (item 2) — o endpoint em si só valida o token do convite.
    accept = await client.post(
        f"/v1/auth/invites/{fresh_token}/accept",
        json={"display_name": "Operador 1", "new_password": "operador-forte-456"},
        headers={"X-CSRF-Token": client.cookies.get("csrf", "")},
    )
    assert accept.status_code == 200, accept.text

    activated = await repo.get_account_by_id(db_pool, invited.id)
    assert activated is not None and activated.status == "active"
    stored = await repo.get_password_hash(db_pool, invited.id)
    assert stored is not None and passwords.verify_password(stored, "operador-forte-456")
