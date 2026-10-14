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
    resolved = await repo.resolve_handoff(
        get_pool(),
        ticket_id=ticket_id,
        operator_id=user.id,
        reply=body.reply,
        action_decision=body.action_decision,
    )

    # Resume the paused graph on the SAME thread, with the TICKET OWNER's identity (ADR 0005):
    # the operator may have a different user_id, but the resumed turn must act for the merchant.
    owner_config = graph_config(
        resolved["user_id"],
        resolved["conversation_id"],
        request.state.trace_id,
    )
    graph = request.app.state.graph
    if graph is None:
        raise AppError(503, "service_unavailable", "Agents are not available yet.")
    await graph.ainvoke(
        Command(resume={"reply": body.reply, "action_decision": body.action_decision}),
        config=owner_config,
    )

    updated = await repo.get_handoff(get_pool(), ticket_id)
    if updated is None:  # unreachable: just resolved — defensive
        raise not_found()
    return Handoff.model_validate(updated)
