"""Quando os dois autenticadores chegam no mesmo request, Bearer vence (REQ-SEC-01).

A coerencia com o CSRF middleware (`src/app/core/csrf_middleware.py`) exige isso: o
middleware pula o CSRF em requests Bearer, logo o `current_user` tambem precisa
tratar o Bearer como a identidade, nao o cookie — caso contrario, um atacante poderia
anexar um cookie de outra sessao a um request CLI e trocar de identidade sem passar
pelo CSRF.
"""

from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from app.api.auth import create_token
from app.auth import passwords, repo
from app.core.config import get_settings
from app.db.pool import Pool

pytestmark = pytest.mark.req("REQ-SEC-01")


@pytest.fixture(autouse=True)
def _secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    s = get_settings()
    monkeypatch.setattr(s, "session_secret", SecretStr("x" * 64))
    monkeypatch.setattr(s, "password_pepper", SecretStr("pepper-" * 4))


async def test_bearer_header_wins_over_session_cookie(
    client: httpx.AsyncClient, db_pool: Pool
) -> None:
    # Loga como merchant "alice@loja" e pega o cookie de sessao.
    account_cookie = await repo.create_account(
        db_pool,
        email="alice@loja.example",
        display_name="Alice",
        role="merchant",
        status="active",
    )
    await repo.set_password(db_pool, account_cookie.id, passwords.hash_password("segura-demo-123"))
    login = await client.post(
        "/v1/auth/login",
        json={"email": "alice@loja.example", "password": "segura-demo-123"},
    )
    assert login.status_code == 200
    # O cliente httpx ja segura o cookie `session` entre requests.

    # Confirma: /v1/auth/me pelo cookie devolve Alice (o endpoint responde AccountOut direto).
    me_cookie = await client.get("/v1/auth/me")
    assert me_cookie.status_code == 200
    assert me_cookie.json()["display_name"] == "Alice"
    alice_id = me_cookie.json()["id"]

    # Agora manda o MESMO request com Authorization: Bearer de outra identidade (cliente1988
    # do seed JWT). O Bearer deve vencer e trocar a identidade do request — o /v1/auth/me
    # devolve display_name do seed, nao mais "Alice".
    bearer = {"Authorization": f"Bearer {create_token('cliente1988', 'merchant')}"}
    me_bearer = await client.get("/v1/auth/me", headers=bearer)
    assert me_bearer.status_code == 200, (
        "Bearer de user do seed deveria autenticar via Bearer, mesmo com cookie da Alice presente."
    )
    body = me_bearer.json()
    assert body["id"] == "cliente1988", (
        f"Bearer deveria sobrescrever o cookie (esperado cliente1988, veio {body['id']!r}). "
        f"Alice e {alice_id!r} e nao deveria aparecer aqui."
    )
    assert body["display_name"] != "Alice"
