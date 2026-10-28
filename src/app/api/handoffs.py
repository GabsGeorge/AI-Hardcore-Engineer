"""Operator endpoints for human handoffs (REQ-HITL-03, REQ-HITL-04, REQ-HITL-06, REQ-SEC-06)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from langgraph.types import Command

from app.api.auth import CurrentUser, require_role
from app.api.chat import graph_config
from app.api.schemas import Handoff, HandoffReply, HandoffStatus
from app.core.errors import AppError, not_found
from app.db import repo
from app.db.pool import get_pool

router = APIRouter()

_OPERATOR = require_role("operator", "admin")


@router.get("/v1/handoffs")
async def list_handoffs(
    status: HandoffStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    user: CurrentUser = Depends(_OPERATOR),
) -> dict[str, list[Handoff]]:
    rows = await repo.list_handoffs(get_pool(), status=status, limit=limit)
    return {"items": [Handoff.model_validate(r) for r in rows]}


@router.post("/v1/handoffs/{ticket_id}/reply", response_model=Handoff)
async def reply(
    ticket_id: UUID,
    body: HandoffReply,
    request: Request,
    user: CurrentUser = Depends(_OPERATOR),
) -> Handoff:
    row = await repo.get_handoff(get_pool(), ticket_id)
    if row is None:
        raise not_found()
    if row["status"] != "awaiting_human":
        raise AppError(409, "ticket_closed", "Ticket already resolved or expired.")
    if row.get("pending_action") and body.action_decision is None:
        raise AppError(422, "validation_error", "action_decision is required for this ticket.")
    graph = request.app.state.graph
    if graph is None:
        raise AppError(503, "service_unavailable", "Agents are not available yet.")

    # Claim atômico ANTES do resume: fecha a janela de corrida entre o SELECT acima e o
    # graph.ainvoke, bloqueando resume duplo quando dois operadores batem no reply ao mesmo
    # tempo. Só um ganha o UPDATE; o outro vê operator_id != NULL e recebe 409 aqui.
    claimed = await repo.claim_handoff(get_pool(), ticket_id=ticket_id, operator_id=user.id)
    if claimed is None:
        raise AppError(409, "ticket_closed", "Ticket already resolved or being handled.")

    # Resume BEFORE closing the ticket: the escalation node re-runs from the top and must still
    # see it open. The resumed turn acts as the ticket OWNER, never the operator (ADR 0005).
    try:
        await graph.ainvoke(
            Command(resume={"reply": body.reply, "action_decision": body.action_decision}),
            config=graph_config(row["user_id"], row["conversation_id"], request.state.trace_id),
        )
    except Exception:
        # Resume falhou: libera o claim para que outro operador possa tentar.
        await repo.release_handoff_claim(get_pool(), ticket_id=ticket_id, operator_id=user.id)
        raise
    try:
        await repo.resolve_handoff(
            get_pool(),
            ticket_id=ticket_id,
            operator_id=user.id,
            reply=body.reply,
            action_decision=body.action_decision,
        )
    except AppError as exc:  # another operator closed it between our check and now
        raise AppError(409, "ticket_closed", "Ticket already resolved or expired.") from exc
    # Dois eventos distintos quando houve ação pendente: operator_reply + action_<decision>.
    # O target carrega só o ticket; o reply e params não são copiados para auditoria.
    await repo.insert_audit_event(
        get_pool(),
        actor_id=user.id,
        actor_role=user.role,
        action="operator_reply",
        target=f"ticket:{ticket_id}",
        outcome="allowed",
        trace_id=request.state.trace_id,
    )
    if body.action_decision is not None:
        await repo.insert_audit_event(
            get_pool(),
            actor_id=user.id,
            actor_role=user.role,
            action=f"action_{body.action_decision}d",
            target=f"ticket:{ticket_id}",
            outcome="allowed",
            trace_id=request.state.trace_id,
        )

    updated = await repo.get_handoff(get_pool(), ticket_id)
    if updated is None:  # unreachable: just resolved — defensive
        raise not_found()
    return Handoff.model_validate(updated)
