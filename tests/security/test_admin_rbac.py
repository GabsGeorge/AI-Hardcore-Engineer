"""Operador/lojista acessando /v1/admin/* → 403 forbidden_role (T084 / FR-024)."""

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


async def _login(client: httpx.AsyncClient, db_pool: Pool, *, email: str, role: str) -> None:
    await repo.create_account(
        db_pool, email=email, display_name=f"Teste {role}", role=role, status="active"
    )
    acc = await repo.get_account_by_email(db_pool, email)
    assert acc is not None
    await repo.set_password(db_pool, acc.id, passwords.hash_password("senha-segura-demo-456"))
    r = await client.post(
        "/v1/auth/login", json={"email": email, "password": "senha-segura-demo-456"}
    )
    assert r.status_code == 200


@pytest.mark.req("REQ-SEC-01")
@pytest.mark.parametrize(
    "role,email", [("operator", "op@example.com"), ("merchant", "l@example.com")]
)
async def test_non_admin_cannot_read_admin_endpoints(
    client: httpx.AsyncClient, db_pool: Pool, role: str, email: str
) -> None:
    await _login(client, db_pool, email=email, role=role)
    for path in ("/v1/admin/accounts", "/v1/admin/queue", "/v1/admin/audit"):
        r = await client.get(path)
        assert r.status_code == 403, (path, r.text)
        assert r.json()["error"]["code"] == "forbidden_role"


@pytest.mark.req("REQ-SEC-01")
async def test_non_admin_cannot_mutate_admin_endpoints(
    client: httpx.AsyncClient, db_pool: Pool
) -> None:
    await _login(client, db_pool, email="op@example.com", role="operator")
    csrf = client.cookies["csrf"]
    r = await client.post(
        "/v1/admin/accounts",
        json={"display_name": "X", "email": "x@example.com", "role": "operator"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden_role"
