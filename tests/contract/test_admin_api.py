"""Smoke do contrato specs/002-web-ui/contracts/admin.yaml (T083 / REQ-API-02): os 6 endpoints
existem e devolvem o status code e o shape prometidos para o admin autenticado."""

from __future__ import annotations

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


async def _login_admin(client: httpx.AsyncClient, db_pool: Pool) -> repo.AccountRow:
    acc = await repo.create_account(
        db_pool, email="adm@getnet.example", display_name="Adm", role="admin", status="active"
    )
    await repo.set_password(db_pool, acc.id, passwords.hash_password("adm-senha-forte-123"))
    r = await client.post(
        "/v1/auth/login", json={"email": "adm@getnet.example", "password": "adm-senha-forte-123"}
    )
    assert r.status_code == 200
    return acc


@pytest.mark.req("REQ-API-02")
async def test_contract_shapes(client: httpx.AsyncClient, db_pool: Pool) -> None:
    await _login_admin(client, db_pool)
    csrf = client.cookies["csrf"]

    # GET /accounts
    r = await client.get("/v1/admin/accounts")
    assert r.status_code == 200
    for item in r.json():
        assert set(["id", "email", "display_name", "role", "status"]).issubset(item.keys())

    # POST /accounts (invite)
    r = await client.post(
        "/v1/admin/accounts",
        json={"display_name": "Op", "email": "op@example.com", "role": "operator"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 202
    assert r.json()["status"] == "pending"

    # GET /queue
    r = await client.get("/v1/admin/queue")
    assert r.status_code == 200
    assert {"awaiting_human", "sla_breached_today", "expired_today"}.issubset(r.json().keys())

    # GET /audit
    r = await client.get("/v1/admin/audit", params={"limit": 5})
    assert r.status_code == 200
    assert isinstance(r.json(), list)

    # POST /accounts/{id}/deactivate requires a target that is not the admin itself.
    target = await repo.create_account(
        db_pool, email="x@example.com", display_name="Alvo X", role="merchant", status="active"
    )
    r = await client.post(
        f"/v1/admin/accounts/{target.id}/deactivate", headers={"X-CSRF-Token": csrf}
    )
    assert r.status_code == 204

    # POST /accounts/{id}/activate reverts the above.
    r = await client.post(
        f"/v1/admin/accounts/{target.id}/activate", headers={"X-CSRF-Token": csrf}
    )
    assert r.status_code == 204
