"""POST /v1/chat. Order of checks: auth (401) → user_id mismatch (403 + audit, no agent runs)
→ owned conversation (404) → graph. The message is PII-masked here, before it reaches the graph
state, so raw PII is never persisted in checkpoints (constitution X)."""

import json
from typing import Any, get_args
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from langchain_core.messages import HumanMessage
from langgraph.types import Overwrite
from sse_starlette.sse import EventSourceResponse

from app.api.auth import CurrentUser, current_user
from app.api.limits import check_rate_limit, idempotency_get_or_claim, idempotency_store
from app.api.schemas import ChatRequest, ChatResponse, GuardrailsResult, HandoffRef, RouteNode
from app.core.errors import AppError, forbidden
from app.db import repo
from app.db.pool import get_pool
from app.guardrails.pii import mask
from app.ops.online_eval import schedule_score_turn

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


async def _reject_foreign_user_id(
    body: ChatRequest, user: CurrentUser, request: Request, trace_id: str
) -> None:
    """403 + audit for a payload user_id that differs from the JWT subject (REQ-SEC-07).

    O endpoint vai na metadata para distinguir /v1/chat de /v1/chat/stream nas auditorias."""
    if body.user_id is None or body.user_id == user.id:
        return
    await repo.insert_audit_event(
        get_pool(),
        actor_id=user.id,
        actor_role=user.role,
        action="forbidden_user_mismatch",
        target=f"user:{body.user_id}",
        outcome="denied",
        trace_id=trace_id,
        metadata={"endpoint": request.url.path},
    )
    raise forbidden("forbidden_user_mismatch", "user_id does not match the authenticated user.")


async def _reflect_open_handoff(
    state: dict[str, Any], user_id: str, conversation_id: UUID
) -> dict[str, Any] | None:
    """interrupt() pauses the run before `escalation` reaches the state; read it from the DB."""
    row = await repo.get_latest_handoff_for_conversation(get_pool(), user_id, conversation_id)
    if row is None or row["status"] != "awaiting_human":
        return None
    state["escalation"] = {
        "reason": row["reason"],
        "status": "awaiting_human",
        "ticket_id": str(row["id"]),
        "summary": row["summary"],
        "pending_action": row.get("pending_action"),
    }
    return row


def _graph_or_503(request: Request) -> Any:
    graph = request.app.state.graph
    if graph is None:
        raise AppError(503, "service_unavailable", "Agents are not available yet.")
    return graph


def _schedule_eval(message: str, response: ChatResponse) -> None:
    if response.guardrails.input == "blocked":
        return
    sources = "\n".join(f"- [{s.kind}] {s.title} — {s.url}" for s in response.sources)
    schedule_score_turn(mask(message)[0], response.response, sources, response.trace_id)


@router.post("/v1/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    request: Request,
    user: CurrentUser = Depends(current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ChatResponse:
    trace_id: str = request.state.trace_id
    await _reject_foreign_user_id(body, user, request, trace_id)
    await check_rate_limit(request, user.id)
    body_dict = body.model_dump(mode="json", exclude_none=True)
    cached = await idempotency_get_or_claim(request, user.id, idempotency_key, body_dict)
    if cached is not None:
        return ChatResponse.model_validate(cached)

    graph = _graph_or_503(request)
    conversation_id = await repo.get_or_create_conversation(
        get_pool(), user.id, body.conversation_id
    )
    state = await graph.ainvoke(
        turn_input(body.message), config=graph_config(user.id, conversation_id, trace_id, user.role)
    )
    if state.get("__interrupt__"):
        await _reflect_open_handoff(state, user.id, conversation_id)
    response = build_response(state, conversation_id, trace_id)
    await idempotency_store(
        request, user.id, idempotency_key, body_dict, response.model_dump(mode="json")
    )
    _schedule_eval(body.message, response)
    return response


@router.post("/v1/chat/stream")
async def chat_stream(
    body: ChatRequest, request: Request, user: CurrentUser = Depends(current_user)
) -> EventSourceResponse:
    """SSE variant of /v1/chat: agent_step per node, handoff, then done (contracts/events.md)."""
    trace_id: str = request.state.trace_id
    await _reject_foreign_user_id(body, user, request, trace_id)
    await check_rate_limit(request, user.id)
    graph = _graph_or_503(request)
    conversation_id = await repo.get_or_create_conversation(
        get_pool(), user.id, body.conversation_id
    )
    config = graph_config(user.id, conversation_id, trace_id, user.role)

    async def _generator() -> Any:
        seen: set[str] = set()
        async for chunk in graph.astream(
            turn_input(body.message), config=config, stream_mode="updates"
        ):
            for node in chunk:
                if node not in seen:
                    seen.add(node)
                    yield {"event": "agent_step", "data": json.dumps({"node": node})}
        # Read the reduced state from the checkpoint: stream updates are per-node deltas and
        # merging them by hand would drop the accumulated results/route of earlier nodes.
        snapshot = await graph.aget_state(config)
        state = dict(snapshot.values)
        if any(task.interrupts for task in snapshot.tasks):
            row = await _reflect_open_handoff(state, user.id, conversation_id)
            if row is not None:
                yield {
                    "event": "handoff",
                    "data": json.dumps({"status": "awaiting_human", "ticket_id": str(row["id"])}),
                }
        response = build_response(state, conversation_id, trace_id)
        _schedule_eval(body.message, response)
        yield {"event": "done", "data": json.dumps(response.model_dump(mode="json"))}

    return EventSourceResponse(_generator())
