"""Ação com efeito colateral (open_dispute) exige aprovação do operador (REQ-HITL-04).

- ``request_action_approval`` devolve ``decision="pending"`` sem executar nada;
- o endpoint POST /v1/handoffs/{id}/reply exige ``action_decision`` quando o ticket carrega
  um ``pending_action``: ausência → 422;
- ``approve`` resolve o ticket com ``approved``; ``reject`` com ``rejected``.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import httpx
import pytest

from app.api.auth import create_token
from app.db.pool import Pool
from app.tools.escalation_tools import request_action_approval
from app.tools.interfaces import OpenDisputeParams, RequestActionApprovalInput


@pytest.fixture
def operator_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token('operador01', 'operator')}"}


@pytest.mark.req("REQ-HITL-04")
async def test_request_action_approval_does_not_execute() -> None:
    args = RequestActionApprovalInput(
        action="open_dispute",
        params=OpenDisputeParams(transaction_id="tx-123", reason="estorno indevido"),
    )
    out = await request_action_approval(args, {"configurable": {}})
    assert out.decision == "pending"
    assert UUID(out.ticket_id)


async def _open_pending_ticket(db_pool: Pool, user_id: str) -> tuple[str, str]:
    """Insere direto no banco uma conversa + handoff com pending_action."""
    conversation_id = uuid4()
    ticket_id = uuid4()
    async with db_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO conversations (id, user_id) VALUES (%s, %s)",
            (conversation_id, user_id),
        )
        await conn.execute(
            "INSERT INTO handoffs (id, conversation_id, user_id, reason, summary, context,"
            " pending_action, sla_due_at, expires_at) VALUES (%s, %s, %s, %s, %s, %s, %s,"
            " now() + interval '15 min', now() + interval '24 hours')",
            (
                ticket_id,
                conversation_id,
                user_id,
                "side_effect_action",
                "Lojista pediu abertura de contestação para a venda tx-123.",
                '{"route": ["supervisor", "escalation"]}',
                '{"type": "open_dispute", "params": {"transaction_id": "tx-123",'
                ' "reason": "estorno indevido"}, "decision": "pending"}',
            ),
        )
        await conn.execute(
            "UPDATE conversations SET handoff_status = 'awaiting_human' WHERE id = %s",
            (conversation_id,),
        )
    return str(ticket_id), str(conversation_id)


@pytest.mark.req("REQ-HITL-04")
async def test_reply_without_decision_on_pending_action_is_422(
    client: httpx.AsyncClient, db_pool: Pool, operator_headers: dict[str, str]
) -> None:
    ticket_id, _ = await _open_pending_ticket(db_pool, "cliente1988")
    resp = await client.post(
        f"/v1/handoffs/{ticket_id}/reply",
        json={"reply": "Vou abrir a contestação."},
        headers=operator_headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


@pytest.mark.req("REQ-HITL-04")
async def test_approve_resolves_ticket_with_approved_decision(
    client: httpx.AsyncClient, db_pool: Pool, operator_headers: dict[str, str]
) -> None:
    ticket_id, _ = await _open_pending_ticket(db_pool, "cliente1988")
    resp = await client.post(
        f"/v1/handoffs/{ticket_id}/reply",
        json={"reply": "Contestação aprovada.", "action_decision": "approve"},
        headers=operator_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "resolved"
    assert body["pending_action"]["decision"] == "approved"


@pytest.mark.req("REQ-HITL-04")
async def test_reject_resolves_ticket_with_rejected_decision(
    client: httpx.AsyncClient, db_pool: Pool, operator_headers: dict[str, str]
) -> None:
    ticket_id, _ = await _open_pending_ticket(db_pool, "cliente1988")
    resp = await client.post(
        f"/v1/handoffs/{ticket_id}/reply",
        json={"reply": "Não vou abrir contestação agora.", "action_decision": "reject"},
        headers=operator_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "resolved"
    assert body["pending_action"]["decision"] == "rejected"
