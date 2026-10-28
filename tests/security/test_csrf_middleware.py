"""Global CSRF middleware (item 2): every mutating cookie-authed endpoint rejects a
missing/invalid ``X-CSRF-Token`` with 403 ``csrf_failed``. Bearer requests bypass CSRF
entirely (CLI/API usage). Each listed endpoint gets its own parametrised check so a
regression on a single route is pinpointed in the test name.
"""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from app.api.auth import create_token
from app.auth import passwords, repo
from app.db.pool import Pool


async def _login_merchant_cookie(client: httpx.AsyncClient, db_pool: Pool) -> repo.AccountRow:
    """Create a merchant with the same ``users.id`` the graph expects for cliente1988 and log
    in via /v1/auth/login so the cookie jar carries ``session`` + ``csrf``."""
    account = await repo.create_account(
        db_pool,
        email="csrfuser@getnet.example",
        display_name="Lojista CSRF",
        role="merchant",
        status="active",
    )
    await repo.set_password(db_pool, account.id, passwords.hash_password("csrf-senha-forte-123"))
    r = await client.post(
        "/v1/auth/login",
        json={"email": "csrfuser@getnet.example", "password": "csrf-senha-forte-123"},
    )
    assert r.status_code == 200, r.text
    return account


# Each tuple: endpoint id → (method, path builder, json body or None).
# ``path`` may need the merchant account id or a fake uuid; the middleware runs BEFORE
# the route logic, so even a non-existent id still triggers the CSRF check first.
_PROTECTED = [
    ("chat", "POST", "/v1/chat", {"message": "oi"}),
    ("chat_stream", "POST", "/v1/chat/stream", {"message": "oi"}),
    ("handoff_reply", "POST", f"/v1/handoffs/{uuid4()}/reply", {"reply": "ok"}),
    ("feedback", "POST", "/v1/feedback", {"conversation_id": str(uuid4()), "rating": "up"}),
    ("me_data_delete", "DELETE", "/v1/me/data", None),
    ("me_account_delete", "DELETE", "/v1/me/account", None),
]


@pytest.mark.req("REQ-SEC-01")
@pytest.mark.parametrize("endpoint_id,method,path,body", _PROTECTED, ids=[e[0] for e in _PROTECTED])
async def test_cookie_mutation_without_csrf_is_403(
    client: httpx.AsyncClient,
    db_pool: Pool,
    endpoint_id: str,
    method: str,
    path: str,
    body: dict[str, object] | None,
) -> None:
    await _login_merchant_cookie(client, db_pool)
    # Drop the csrf header on purpose; the cookie is still in the jar.
    r = await client.request(method, path, json=body)
    assert r.status_code == 403, f"{endpoint_id}: expected 403, got {r.status_code} ({r.text})"
    payload = r.json()
    assert payload["error"]["code"] == "csrf_failed"


@pytest.mark.req("REQ-SEC-01")
@pytest.mark.parametrize("endpoint_id,method,path,body", _PROTECTED, ids=[e[0] for e in _PROTECTED])
async def test_cookie_mutation_with_wrong_csrf_is_403(
    client: httpx.AsyncClient,
    db_pool: Pool,
    endpoint_id: str,
    method: str,
    path: str,
    body: dict[str, object] | None,
) -> None:
    await _login_merchant_cookie(client, db_pool)
    r = await client.request(method, path, json=body, headers={"X-CSRF-Token": "forjado"})
    assert r.status_code == 403, f"{endpoint_id}: expected 403, got {r.status_code}"
    assert r.json()["error"]["code"] == "csrf_failed"


@pytest.mark.req("REQ-SEC-01")
async def test_bearer_requests_bypass_csrf(client: httpx.AsyncClient) -> None:
    """CLI / API usage via Bearer must not be blocked by the CSRF middleware (there is no
    cookie origin to protect). The actual endpoint may answer 200/4xx on business grounds —
    we only prove the middleware did NOT emit ``csrf_failed``."""
    token = create_token("cliente1988", "merchant")
    r = await client.post(
        "/v1/chat",
        json={"message": "oi"},
        headers={"Authorization": f"Bearer {token}"},
    )
    if r.status_code == 403:
        assert r.json()["error"]["code"] != "csrf_failed", (
            f"Bearer path was blocked by CSRF middleware: {r.text}"
        )
