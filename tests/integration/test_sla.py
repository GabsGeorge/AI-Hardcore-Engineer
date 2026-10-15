"""Scheduler de SLA, expiração e expurgo (REQ-HITL-05, REQ-SEC-09).

Simulamos o relógio deslocando as colunas de prazo direto no banco (``sla_due_at = now() - '1 min'``
etc.) e disparamos ``run_tick`` manualmente — a tarefa periódica em si é só o ``asyncio.sleep``
em cima dessa função.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.db.pool import Pool
from app.ops.scheduler import run_tick


async def _open_ticket(db_pool: Pool, user_id: str = "cliente1988") -> tuple[str, str]:
    conversation_id = uuid4()
    ticket_id = uuid4()
    async with db_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO conversations (id, user_id) VALUES (%s, %s)",
            (conversation_id, user_id),
        )
        await conn.execute(
            "INSERT INTO handoffs (id, conversation_id, user_id, reason, summary,"
            " sla_due_at, expires_at) VALUES (%s, %s, %s, %s, %s,"
            " now() + interval '15 min', now() + interval '24 hours')",
            (ticket_id, conversation_id, user_id, "human_request", "Pediu humano."),
        )
        await conn.execute(
            "UPDATE conversations SET handoff_status = 'awaiting_human' WHERE id = %s",
            (conversation_id,),
        )
    return str(ticket_id), str(conversation_id)


@pytest.mark.req("REQ-HITL-05")
async def test_sla_breach_promotes_priority_to_high(db_pool: Pool) -> None:
    ticket_id, _ = await _open_ticket(db_pool)
    # Simula "16 min depois": SLA (15 min) estourado.
    async with db_pool.connection() as conn:
        await conn.execute(
            "UPDATE handoffs SET sla_due_at = now() - interval '1 min' WHERE id = %s",
            (ticket_id,),
        )
    result = await run_tick(db_pool, with_retention=False)
    assert result["sla"] >= 1
    async with db_pool.connection() as conn:
        row = await (
            await conn.execute("SELECT priority FROM handoffs WHERE id = %s", (ticket_id,))
        ).fetchone()
    assert row is not None and row["priority"] == "high"


@pytest.mark.req("REQ-HITL-05")
async def test_expired_ticket_marks_expired_and_clears_conversation(db_pool: Pool) -> None:
    ticket_id, conversation_id = await _open_ticket(db_pool)
    # Simula "24 h 1 min depois".
    async with db_pool.connection() as conn:
        await conn.execute(
            "UPDATE handoffs SET expires_at = now() - interval '1 min' WHERE id = %s",
            (ticket_id,),
        )
    result = await run_tick(db_pool, with_retention=False)
    assert result["expired"] >= 1
    async with db_pool.connection() as conn:
        ticket = await (
            await conn.execute("SELECT status FROM handoffs WHERE id = %s", (ticket_id,))
        ).fetchone()
        conv = await (
            await conn.execute(
                "SELECT handoff_status FROM conversations WHERE id = %s", (conversation_id,)
            )
        ).fetchone()
    assert ticket is not None and ticket["status"] == "expired"
    assert conv is not None and conv["handoff_status"] == "none"


@pytest.mark.req("REQ-SEC-09")
async def test_retention_sweep_removes_old_conversations_and_audit(db_pool: Pool) -> None:
    """Expurgo diário remove conversas inativas há mais do que ``retention_conversation_days``."""
    user_id = "cliente1988"
    conversation_id = uuid4()
    async with db_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO conversations (id, user_id, last_activity_at) VALUES"
            " (%s, %s, now() - interval '200 days')",
            (conversation_id, user_id),
        )
        await conn.execute(
            "INSERT INTO audit_events (ts, actor_id, actor_role, action, target, outcome,"
            " trace_id) VALUES (now() - interval '400 days', %s, 'merchant', 'login',"
            " 'self', 'allowed', %s)",
            (user_id, "0" * 32),
        )
    result = await run_tick(db_pool, with_retention=True)
    assert result["retention"]["conversations"] >= 1
    assert result["retention"]["audit_events"] >= 1
