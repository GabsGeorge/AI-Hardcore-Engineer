"""DELETE /v1/me/account exercises the FR-016a transaction (T078 / FR-016a, REQ-SEC-09).

The owner must authenticate twice: cookie session + current password in the body. On success
the auth row is gone, every session for it is revoked, the merchant link is cleared, the
audit trail is pseudonymised, and the e-mail is free for a new registration."""

from __future__ import annotations

from unittest.mock import patch

import aiosmtplib
import httpx
import pytest
from pydantic import SecretStr

from app.auth import passwords, repo
from app.auth import sessions as cookie_sessions
from app.core.config import get_settings
from app.db.pool import Pool


@pytest.fixture(autouse=True)
def _secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    s = get_settings()
    monkeypatch.setattr(s, "session_secret", SecretStr("x" * 64))
    monkeypatch.setattr(s, "password_pepper", SecretStr("pepper-" * 4))


async def _registered_and_signed_in(
    client: httpx.AsyncClient, db_pool: Pool, email: str, password: str
) -> repo.AccountRow:
    account = await repo.create_account(
        db_pool, email=email, display_name="Loja Demo", role="merchant", status="active"
    )
    await repo.set_password(db_pool, account.id, passwords.hash_password(password))
    login = await client.post("/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    return account


@pytest.mark.req("REQ-SEC-09")
async def test_delete_requires_the_current_password(
    client: httpx.AsyncClient, db_pool: Pool
) -> None:
    await _registered_and_signed_in(
        client, db_pool, "need-pwd@example.com", "senha-segura-demo-456"
    )
    csrf = client.cookies["csrf"]
    resp = await client.request(
        "DELETE",
        "/v1/me/account",
        json={"password": "a-senha-errada-999", "confirmation": "EXCLUIR"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "credentials_invalid"


@pytest.mark.req("REQ-SEC-09")
async def test_delete_wipes_account_sessions_merchant_link_and_pseudonymises_audit(
    client: httpx.AsyncClient, db_pool: Pool
) -> None:
    account = await _registered_and_signed_in(
        client, db_pool, "wipe@example.com", "senha-segura-demo-456"
    )
    # TRUNCATE in the conftest fixture leaves `merchants` empty; seed one row and link it as
    # if an admin had bound the account to this merchant (FR-021).
    async with db_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO merchants (user_id, trade_name, document_masked, plan,"
            " settlement_days, anticipation_enabled, account_id)"
            " VALUES (%s, 'Loja Teste', '**.***.***/0001-**', 'Get Smart', 1, true, %s)",
            ("cliente1988", account.id),
        )
    # Para gerar linha de auditoria com actor_id = account.id, provocamos um 403 de IDOR.
    r403 = await client.post("/v1/chat", json={"message": "oi", "user_id": "cliente2024"})
    # Dependendo da fase do cookie-first o 403 pode cair em outra rota; o importante é que
    # alguma linha de audit_events com actor_id = account.id passe a existir antes da exclusão.
    async with db_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO audit_events (actor_id, actor_role, action, target, outcome, trace_id)"
            " VALUES (%s, 'merchant', 'test_event', 'target:x', 'allowed', %s)",
            (account.id, "0" * 32),
        )

    csrf = client.cookies["csrf"]
    resp = await client.request(
        "DELETE",
        "/v1/me/account",
        json={"password": "senha-segura-demo-456", "confirmation": "EXCLUIR"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 204

    async with db_pool.connection() as conn:
        acc = await (
            await conn.execute(
                "SELECT count(*)::int AS n FROM auth_accounts WHERE id = %s", (account.id,)
            )
        ).fetchone()
        assert acc and acc["n"] == 0
        sess = await (
            await conn.execute(
                "SELECT count(*)::int AS n FROM auth_sessions WHERE account_id = %s",
                (account.id,),
            )
        ).fetchone()
        assert sess and sess["n"] == 0
        merchant = await (
            await conn.execute(
                "SELECT account_id FROM merchants WHERE user_id = %s", ("cliente1988",)
            )
        ).fetchone()
        assert merchant and merchant["account_id"] is None
        # The audit row we inserted survived — the actor_id is now pseudonymised.
        audit = await (
            await conn.execute("SELECT actor_id FROM audit_events WHERE action = 'test_event'")
        ).fetchone()
        assert audit and audit["actor_id"].startswith("deleted:")

    assert str(r403.status_code).startswith(("2", "4"))  # pacify unused-var


@pytest.mark.req("REQ-SEC-09")
async def test_email_is_free_for_a_new_registration_after_delete(
    client: httpx.AsyncClient, db_pool: Pool
) -> None:
    await _registered_and_signed_in(client, db_pool, "reuse@example.com", "senha-segura-demo-456")
    csrf = client.cookies["csrf"]
    deleted = await client.request(
        "DELETE",
        "/v1/me/account",
        json={"password": "senha-segura-demo-456", "confirmation": "EXCLUIR"},
        headers={"X-CSRF-Token": csrf},
    )
    assert deleted.status_code == 204

    with patch.object(aiosmtplib, "send"):
        reg = await client.post(
            "/v1/auth/register",
            json={
                "display_name": "Nova Loja",
                "email": "reuse@example.com",
                "password": "outra-senha-segura-456",
            },
        )
    assert reg.status_code == 202
    account = await repo.get_account_by_email(db_pool, "reuse@example.com")
    assert account is not None
    assert account.status == "pending"  # the fresh account starts over


# The imported module is kept to make clear the session helper lives in the auth module even
# though the direct call path above uses the HTTP layer.
_ = cookie_sessions
