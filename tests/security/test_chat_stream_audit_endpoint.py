"""O audit do 403 em /v1/chat/stream carrega o endpoint na metadata (item 4).

Diferencia /v1/chat de /v1/chat/stream no log de auditoria para que o SOC saiba qual
canal foi usado na tentativa de IDOR."""

from __future__ import annotations

import httpx
import pytest

from app.db.pool import Pool


@pytest.mark.req("REQ-SEC-07")
async def test_chat_stream_403_audit_records_endpoint(
    client: httpx.AsyncClient,
    db_pool: Pool,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    resp = await client.post(
        "/v1/chat/stream",
        json={"message": "oi", "user_id": "cliente2024"},
        headers=auth_headers["cliente1988"],
    )
    assert resp.status_code == 403
    async with db_pool.connection() as conn:
        row = await (
            await conn.execute(
                "SELECT metadata FROM audit_events"
                " WHERE action = 'forbidden_user_mismatch' AND actor_id = 'cliente1988'"
                " ORDER BY ts DESC LIMIT 1"
            )
        ).fetchone()
    assert row is not None
    assert row["metadata"].get("endpoint") == "/v1/chat/stream"


@pytest.mark.req("REQ-SEC-07")
async def test_chat_403_audit_records_endpoint(
    client: httpx.AsyncClient,
    db_pool: Pool,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    resp = await client.post(
        "/v1/chat",
        json={"message": "oi", "user_id": "cliente2024"},
        headers=auth_headers["cliente1988"],
    )
    assert resp.status_code == 403
    async with db_pool.connection() as conn:
        row = await (
            await conn.execute(
                "SELECT metadata FROM audit_events"
                " WHERE action = 'forbidden_user_mismatch' AND actor_id = 'cliente1988'"
                " ORDER BY ts DESC LIMIT 1"
            )
        ).fetchone()
    assert row is not None
    assert row["metadata"].get("endpoint") == "/v1/chat"
