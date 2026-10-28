"""Limite de conexões SSE no canal /v1/conversations/{id}/events (item 4).

Sem teto, um cliente com bug ou malicioso pode acumular canais e segurar workers do servidor.
Testamos o mecanismo de acquire/release direto porque o TestClient httpx bufferiza o
EventSourceResponse e não deixa duas conexões conviverem no mesmo loop."""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from app.api import conversations as conv_mod
from app.core.errors import AppError
from app.db.pool import Pool


async def _owned_conversation(db_pool: Pool, user_id: str) -> str:
    conversation_id = uuid4()
    async with db_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO conversations (id, user_id) VALUES (%s, %s)",
            (conversation_id, user_id),
        )
    return str(conversation_id)


@pytest.mark.req("REQ-SEC-11")
async def test_acquire_raises_429_when_user_hits_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(conv_mod, "MAX_SSE_PER_USER", 2)
    conv_mod._sse_connections.clear()
    await conv_mod._acquire_sse_slot("cliente1988")
    await conv_mod._acquire_sse_slot("cliente1988")
    with pytest.raises(AppError) as exc:
        await conv_mod._acquire_sse_slot("cliente1988")
    assert exc.value.status == 429
    assert exc.value.code == "too_many_connections"


@pytest.mark.req("REQ-SEC-11")
async def test_release_frees_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(conv_mod, "MAX_SSE_PER_USER", 1)
    conv_mod._sse_connections.clear()
    await conv_mod._acquire_sse_slot("cliente1988")
    await conv_mod._release_sse_slot("cliente1988")
    # Depois do release o counter zera e um novo acquire passa.
    await conv_mod._acquire_sse_slot("cliente1988")
    assert conv_mod._sse_connections.get("cliente1988") == 1


@pytest.mark.req("REQ-SEC-11")
async def test_separate_users_have_independent_quotas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(conv_mod, "MAX_SSE_PER_USER", 1)
    conv_mod._sse_connections.clear()
    await conv_mod._acquire_sse_slot("cliente1988")
    # Outro usuário tem seu próprio contador — não é um limite global.
    await conv_mod._acquire_sse_slot("cliente2024")
    assert conv_mod._sse_connections["cliente1988"] == 1
    assert conv_mod._sse_connections["cliente2024"] == 1


@pytest.mark.req("REQ-SEC-11")
async def test_events_endpoint_returns_429_when_slot_exhausted(
    client: httpx.AsyncClient,
    db_pool: Pool,
    auth_headers: dict[str, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pré-ocupa o slot via acquire direto e verifica que o endpoint devolve 429."""
    monkeypatch.setattr(conv_mod, "MAX_SSE_PER_USER", 1)
    conv_mod._sse_connections.clear()
    conv_id = await _owned_conversation(db_pool, "cliente1988")
    await conv_mod._acquire_sse_slot("cliente1988")
    try:
        resp = await client.get(
            f"/v1/conversations/{conv_id}/events",
            headers=auth_headers["cliente1988"],
        )
        assert resp.status_code == 429
        assert resp.json()["error"]["code"] == "too_many_connections"
    finally:
        await conv_mod._release_sse_slot("cliente1988")
