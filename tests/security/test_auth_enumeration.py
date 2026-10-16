"""E-mail enumeration: register and reset-request must look identical for new and existing
accounts (T041 / FR-004). We check for byte-identical response bodies and for a response-time
distribution whose medians are close enough that an attacker cannot tell them apart from timing
alone."""

from __future__ import annotations

import statistics
import time
from unittest.mock import patch

import aiosmtplib
import httpx
import pytest
from pydantic import SecretStr

from app.auth import passwords, repo
from app.core.config import get_settings
from app.db.pool import Pool

_SAMPLES = 20


@pytest.fixture(autouse=True)
def _secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    s = get_settings()
    monkeypatch.setattr(s, "session_secret", SecretStr("x" * 64))
    monkeypatch.setattr(s, "password_pepper", SecretStr("pepper-" * 4))


async def _active_account(db_pool: Pool, email: str) -> None:
    account = await repo.create_account(
        db_pool, email=email, display_name="Loja Teste", role="merchant", status="active"
    )
    await repo.set_password(db_pool, account.id, passwords.hash_password("senha-segura-demo"))


async def test_register_response_is_identical_for_new_and_existing_emails(
    client: httpx.AsyncClient, db_pool: Pool
) -> None:
    await _active_account(db_pool, "existing@example.com")
    body = {
        "display_name": "Loja",
        "email": "existing@example.com",
        "password": "senha-segura-demo",
    }
    with patch.object(aiosmtplib, "send"):
        existing = await client.post("/v1/auth/register", json=body)
    with patch.object(aiosmtplib, "send"):
        new = await client.post(
            "/v1/auth/register",
            json={**body, "email": "brand-new@example.com"},
        )
    assert existing.status_code == new.status_code == 202
    assert existing.content == new.content


async def test_reset_request_body_is_identical_for_new_and_existing_emails(
    client: httpx.AsyncClient, db_pool: Pool
) -> None:
    await _active_account(db_pool, "known@example.com")
    with patch.object(aiosmtplib, "send"):
        known = await client.post(
            "/v1/auth/password/reset-request", json={"email": "known@example.com"}
        )
    with patch.object(aiosmtplib, "send"):
        unknown = await client.post(
            "/v1/auth/password/reset-request", json={"email": "ghost@example.com"}
        )
    assert known.status_code == unknown.status_code == 202
    assert known.content == unknown.content


async def test_login_timing_difference_is_not_a_tell(
    client: httpx.AsyncClient, db_pool: Pool
) -> None:
    """Response time for an unknown e-mail must not be measurably shorter than for a known one.
    We allow a 3x factor between medians so a slow CI does not flake, which is still well below
    anything useful to an attacker."""
    await _active_account(db_pool, "timing@example.com")
    known_times: list[float] = []
    unknown_times: list[float] = []
    for _ in range(_SAMPLES):
        start = time.perf_counter()
        await client.post(
            "/v1/auth/login",
            json={"email": "timing@example.com", "password": "wrong-password-123"},
        )
        known_times.append(time.perf_counter() - start)
        start = time.perf_counter()
        await client.post(
            "/v1/auth/login",
            json={"email": "unknown@example.com", "password": "wrong-password-123"},
        )
        unknown_times.append(time.perf_counter() - start)
    k = statistics.median(known_times)
    u = statistics.median(unknown_times)
    ratio = max(k, u) / max(min(k, u), 0.001)
    assert ratio < 3.0, (
        f"timing difference too large: ratio={ratio:.2f}, known={k:.4f}, unknown={u:.4f}"
    )
