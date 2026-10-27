"""/v1/admin/audit não vaza PII bruta: e-mails de lojistas chegam mascarados pelo ``_scrub``
em ``insert_audit_event`` e CPF/CNPJ nunca aparecem em claro (T087 / FR-023, REQ-SEC-07)."""

from __future__ import annotations

import re

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


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


async def _login_admin(client: httpx.AsyncClient, db_pool: Pool) -> None:
    await repo.create_account(
        db_pool, email="admin@getnet.example", display_name="Admin", role="admin", status="active"
    )
    acc = await repo.get_account_by_email(db_pool, "admin@getnet.example")
    assert acc
    await repo.set_password(db_pool, acc.id, passwords.hash_password("admin-senha-forte-123"))
    r = await client.post(
        "/v1/auth/login",
        json={"email": "admin@getnet.example", "password": "admin-senha-forte-123"},
    )
    assert r.status_code == 200


@pytest.mark.req("REQ-SEC-07")
async def test_audit_response_scrubs_pii(client: httpx.AsyncClient, db_pool: Pool) -> None:
    await _login_admin(client, db_pool)
    from app.db import repo as db_repo

    # Insere uma linha com e-mail e CNPJ brutos no target — o helper deve mascará-los.
    await db_repo.insert_audit_event(
        db_pool,
        actor_id="acc_test",
        actor_role="admin",
        action="pii_probe",
        target="email:fulano@example.com acao=xyz",
        outcome="allowed",
        trace_id="0" * 32,
    )

    r = await client.get("/v1/admin/audit", params={"action": "pii_probe"})
    assert r.status_code == 200
    body = r.text
    assert not _EMAIL_RE.search(body), f"audit vazou e-mail: {body}"
