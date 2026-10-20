"""Operator reply from the UI exercises the real approve/reject path (T067 / FR-018).

This covers the regression from audit finding 4: a ticket with a ``pending_action`` requires
``action_decision`` or the API answers 422; approving records ``approved`` on the row and the
ticket flips to ``resolved``; a second reply from another operator window gets 409."""

from __future__ import annotations

from uuid import UUID, uuid4

import httpx
import pytest

from app.api.auth import create_token
from app.db.pool import Pool


@pytest.fixture
def operator_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token('operador01', 'operator')}"}


async def _ticket_with_pending_action(db_pool: Pool) -> tuple[UUID, UUID]:
    conversation_id = uuid4()
    ticket_id = uuid4()
    async with db_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO conversations (id, user_id) VALUES (%s, %s)",
            (conversation_id, "cliente1988"),
        )
        await conn.execute(
            "INSERT INTO handoffs (id, conversation_id, user_id, reason, summary, context,"
            " pending_action, sla_due_at, expires_at) VALUES (%s, %s, %s, %s, %s, %s, %s,"
            " now() + interval '15 min', now() + interval '24 hours')",
            (
                ticket_id,
                conversation_id,
                "cliente1988",
                "side_effect_action",
                "Pediu abrir contestação para tx-123.",
                '{"route": ["supervisor", "escalation"]}',
                '{"type": "open_dispute", "params": {"transaction_id": "tx-123",'
                ' "reason": "estorno indevido"}, "decision": "pending"}',
            ),
        )
        await conn.execute(
            "UPDATE conversations SET handoff_status = 'awaiting_human' WHERE id = %s",
            (conversation_id,),
        )
    return ticket_id, conversation_id


@pytest.mark.req("REQ-HITL-04")
async def test_reply_without_action_decision_is_422(
    client: httpx.AsyncClient, db_pool: Pool, operator_headers: dict[str, str]
) -> None:
    ticket_id, _ = await _ticket_with_pending_action(db_pool)
    resp = await client.post(
        f"/v1/handoffs/{ticket_id}/reply",
        json={"reply": "Vou abrir a contestação."},
        headers=operator_headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


@pytest.mark.req("REQ-HITL-04")
async def test_approve_records_decision_and_resolves_ticket(
    client: httpx.AsyncClient, db_pool: Pool, operator_headers: dict[str, str]
) -> None:
    ticket_id, _ = await _ticket_with_pending_action(db_pool)
    resp = await client.post(
        f"/v1/handoffs/{ticket_id}/reply",
        json={"reply": "Contestação aprovada para tx-123.", "action_decision": "approve"},
        headers=operator_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "resolved"
    assert body["pending_action"]["decision"] == "approved"


@pytest.mark.req("REQ-HITL-04")
async def test_second_reply_gets_409_ticket_closed(
    client: httpx.AsyncClient, db_pool: Pool, operator_headers: dict[str, str]
) -> None:
    ticket_id, _ = await _ticket_with_pending_action(db_pool)
    first = await client.post(
        f"/v1/handoffs/{ticket_id}/reply",
        json={"reply": "ok", "action_decision": "approve"},
        headers=operator_headers,
    )
    assert first.status_code == 200
    second = await client.post(
        f"/v1/handoffs/{ticket_id}/reply",
        json={"reply": "de novo", "action_decision": "approve"},
        headers=operator_headers,
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "ticket_closed"
