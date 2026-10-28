"""Bloqueio de resume duplo no POST /v1/handoffs/{id}/reply (item 4).

Antes do fix, dois operadores podiam passar pelo SELECT inicial e cair simultaneamente no
graph.ainvoke(Command(resume=...)): a ação lateral podia executar duas vezes antes do CAS do
resolve_handoff decidir o vencedor. O claim atômico via operator_id fecha essa janela."""

from __future__ import annotations

from uuid import UUID, uuid4

import httpx
import pytest

from app.api.auth import create_token
from app.db import repo
from app.db.pool import Pool


@pytest.fixture
def operator_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token('operador01', 'operator')}"}


async def _ensure_operator(db_pool: Pool, operator_id: str) -> None:
    async with db_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO users (id, role, display_name) VALUES (%s, 'operator', %s)"
            " ON CONFLICT (id) DO NOTHING",
            (operator_id, f"Operador {operator_id}"),
        )


async def _awaiting_ticket(db_pool: Pool) -> tuple[UUID, UUID]:
    conversation_id = uuid4()
    ticket_id = uuid4()
    async with db_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO conversations (id, user_id) VALUES (%s, %s)",
            (conversation_id, "cliente1988"),
        )
        await conn.execute(
            "INSERT INTO handoffs (id, conversation_id, user_id, reason, summary, context,"
            " sla_due_at, expires_at) VALUES (%s, %s, %s, %s, %s, %s,"
            " now() + interval '15 min', now() + interval '24 hours')",
            (
                ticket_id,
                conversation_id,
                "cliente1988",
                "human_request",
                "Pediu ajuda humana.",
                '{"route": ["supervisor", "escalation"]}',
            ),
        )
    return ticket_id, conversation_id


@pytest.mark.req("REQ-HITL-04")
async def test_claim_handoff_wins_once(db_pool: Pool) -> None:
    await _ensure_operator(db_pool, "operador02")
    ticket_id, _ = await _awaiting_ticket(db_pool)
    first = await repo.claim_handoff(db_pool, ticket_id=ticket_id, operator_id="operador01")
    assert first is not None and first["status"] == "awaiting_human"
    # Segunda tentativa — mesmo que outro operador — deve ver operator_id != NULL e falhar.
    second = await repo.claim_handoff(db_pool, ticket_id=ticket_id, operator_id="operador02")
    assert second is None


@pytest.mark.req("REQ-HITL-04")
async def test_release_claim_lets_another_operator_try(db_pool: Pool) -> None:
    await _ensure_operator(db_pool, "operador02")
    ticket_id, _ = await _awaiting_ticket(db_pool)
    assert await repo.claim_handoff(db_pool, ticket_id=ticket_id, operator_id="operador01")
    await repo.release_handoff_claim(db_pool, ticket_id=ticket_id, operator_id="operador01")
    retry = await repo.claim_handoff(db_pool, ticket_id=ticket_id, operator_id="operador02")
    assert retry is not None


@pytest.mark.req("REQ-HITL-04")
async def test_reply_with_pre_claimed_ticket_returns_409(
    client: httpx.AsyncClient,
    db_pool: Pool,
    operator_headers: dict[str, str],
) -> None:
    """Simula o outro operador tendo claim antes: segundo request vê 409 antes do graph.ainvoke."""
    await _ensure_operator(db_pool, "operador_other")
    ticket_id, _ = await _awaiting_ticket(db_pool)
    async with db_pool.connection() as conn:
        await conn.execute(
            "UPDATE handoffs SET operator_id = %s WHERE id = %s",
            ("operador_other", ticket_id),
        )
    resp = await client.post(
        f"/v1/handoffs/{ticket_id}/reply",
        json={"reply": "tentando resumir"},
        headers=operator_headers,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "ticket_closed"
