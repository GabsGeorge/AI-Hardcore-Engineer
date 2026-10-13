"""POST /v1/chat. Order of checks: auth (401) → user_id mismatch (403 + audit, no agent runs)
→ owned conversation (404) → graph. The message is PII-masked here, before it reaches the graph
state, so raw PII is never persisted in checkpoints (constitution X)."""

from typing import Any, get_args
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from langchain_core.messages import HumanMessage
from langgraph.types import Overwrite

from app.api.auth import CurrentUser, current_user
from app.api.schemas import ChatRequest, ChatResponse, GuardrailsResult, HandoffRef, RouteNode
from app.core.errors import AppError, forbidden
from app.db import repo
from app.db.pool import get_pool
from app.guardrails.pii import mask

router = APIRouter()

_ROUTE_NODES = set(get_args(RouteNode))


def graph_config(
    user_id: str, conversation_id: UUID | str, trace_id: str, user_role: str = "merchant"
) -> dict[str, Any]:
    """Identity lives only in `configurable`, never in the state the LLM sees (ADR 0005)."""
    return {
        "configurable": {
            "thread_id": f"{user_id}:{conversation_id}",
            "user_id": user_id,
            "user_role": user_role,
            "trace_id": trace_id,
        },
        "recursion_limit": 25,
    }


def turn_input(message: str) -> dict[str, Any]:
    masked, found = mask(message)
    return {
        "messages": [HumanMessage(content=masked)],
        "input_pii": found,
        "language": None,
        "plan": None,
        "attempts": 0,
        "step": 0,
        "escalation": None,
        "final_response": None,
        # Per-turn accumulators start empty on every new message of the same thread.
        "results": Overwrite([]),
        "route_trace": Overwrite([]),
        "guardrail_flags": Overwrite([]),
        "tokens_used": Overwrite(0),
    }


def _flag(flags: list[str], stage: str, order: tuple[str, ...]) -> str:
    present = {f.split(":", 1)[1] for f in flags if f.startswith(f"{stage}:")}
    return next((v for v in order if v in present), "pass")


def build_response(state: dict[str, Any], conversation_id: UUID, trace_id: str) -> ChatResponse:
    results = state.get("results") or []
    ok = [r for r in results if not r.get("error")]
    flags = state.get("guardrail_flags") or []
    escalation = state.get("escalation") or {}
    sources: dict[str, dict[str, Any]] = {}
    for r in ok:
        for src in r.get("sources", []):
            sources.setdefault(src["url"], src)
    return ChatResponse(
        response=state.get("final_response") or "",
        conversation_id=conversation_id,
        route=[n for n in state.get("route_trace") or [] if n in _ROUTE_NODES],
        sources=list(sources.values()),
        tools_used=[t for r in results for t in r.get("tools_used", [])],
        confidence=min((r["confidence"] for r in ok), default=0.0),
        handoff=HandoffRef(
            status=escalation.get("status", "none"), ticket_id=escalation.get("ticket_id")
        ),
        guardrails=GuardrailsResult(
            input=_flag(flags, "input", ("blocked", "masked")),
            output=_flag(flags, "output", ("blocked", "rewritten")),
        ),
        trace_id=trace_id,
    )


@router.post("/v1/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest, request: Request, user: CurrentUser = Depends(current_user)
) -> ChatResponse:
    trace_id: str = request.state.trace_id
    pool = get_pool()
    if body.user_id is not None and body.user_id != user.id:
        await repo.insert_audit_event(
            pool,
            actor_id=user.id,
            actor_role=user.role,
            action="forbidden_user_mismatch",
            target=f"user:{body.user_id}",
            outcome="denied",
            trace_id=trace_id,
        )
        raise forbidden("forbidden_user_mismatch", "user_id does not match the authenticated user.")

    graph = request.app.state.graph
    if graph is None:
        raise AppError(503, "service_unavailable", "Agents are not available yet.")
    conversation_id = await repo.get_or_create_conversation(pool, user.id, body.conversation_id)
    state = await graph.ainvoke(
        turn_input(body.message), config=graph_config(user.id, conversation_id, trace_id, user.role)
    )
    return build_response(state, conversation_id, trace_id)
