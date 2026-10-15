"""Escalation specialist: ticket, pause with interrupt() and resume with the human reply.

Steps:
1. Build a short summary of the situation (one LLM call, bounded).
2. Open a handoff row (repo.create_handoff) and sign off: `handoff.status = awaiting_human`.
3. Pause the graph with `interrupt({ticket_id, reason, summary})`; the API returns 200 with
   the pending handoff. The operator replies via POST /v1/handoffs/{id}/reply, which calls
   `Command(resume={"reply", "action_decision"})` on the same thread_id.
4. On resume, incorporate the operator reply in the final AIMessage of the merchant conversation.
   Identity for the resumed turn comes from the ticket's user_id (ADR 0005).
"""

from typing import Any
from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from app.agents.common import make_result
from app.core.config import get_settings
from app.core.llm import get_model
from app.core.prompts import load_prompt
from app.db import repo
from app.db.pool import get_pool
from app.graph.state import AgentState, SubTask
from app.tools.escalation_tools import new_ticket_id

_HUMAN_REPLY = {
    "pt": "Nosso atendente respondeu:",
    "en": "Our human agent replied:",
}


async def _summarise(state: AgentState, language: str) -> str:
    """One LLM call max; a model failure falls back to the merchant's last question."""
    try:
        reply = await get_model("escalation").ainvoke(
            [
                SystemMessage(content=load_prompt("escalation").replace("{language}", language)),
                HumanMessage(
                    content=f"Last merchant question:\n{state['messages'][-1].content}"
                    if state.get("messages")
                    else ""
                ),
            ]
        )
    except Exception:
        last = next(
            (m for m in reversed(state.get("messages") or []) if isinstance(m, HumanMessage)),
            None,
        )
        return str(getattr(last, "content", "")).strip() or "no question provided"
    return str(getattr(reply, "content", "")).strip() or "no summary"


async def escalation_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    conf = config.get("configurable", {})
    user_id = conf.get("user_id", "")
    thread = conf.get("thread_id", "")
    conversation_id = thread.split(":", 1)[1] if ":" in thread else thread
    language = state.get("language") or "pt"
    esc_in: dict[str, Any] = dict(state.get("escalation") or {})
    reason: str = str(esc_in.get("reason") or "human_request")
    pending_action = esc_in.get("pending_action")
    if pending_action is not None and not isinstance(pending_action, dict):
        pending_action = None

    # On resume, LangGraph re-enters this node from the top. Reuse the existing open ticket
    # instead of creating a duplicate (which would reset conversations.handoff_status).
    existing = await repo.get_latest_handoff_for_conversation(
        get_pool(),
        user_id,
        conversation_id if isinstance(conversation_id, UUID) else UUID(conversation_id),
    )
    if existing is not None:
        # Either we are on the resume pass (status=resolved) or the handoff is still open.
        # In both cases reuse it; do NOT create a duplicate (which would reset handoff_status).
        ticket_id = existing["id"]
        summary = existing["summary"]
    else:
        settings = get_settings()
        summary = await _summarise(state, language)
        ticket_id = new_ticket_id()
        await repo.create_handoff(
            get_pool(),
            ticket_id=ticket_id,
            conversation_id=conversation_id,
            user_id=user_id,
            reason=reason,
            summary=summary,
            context={"route": state.get("route_trace") or []},
            pending_action=pending_action,
            sla_minutes=settings.handoff_sla_minutes,
            expiry_hours=settings.handoff_expiry_hours,
        )
        # Trilha de escalação (REQ-SEC-07): o target carrega o id do ticket, sem PII.
        await repo.insert_audit_event(
            get_pool(),
            actor_id=user_id,
            actor_role="merchant",
            action="escalated",
            target=f"ticket:{ticket_id}",
            outcome="allowed",
            trace_id=conf.get("trace_id", ""),
            metadata={"reason": reason},
        )

    # Pause the graph: the API will see this and return handoff.status = awaiting_human.
    resume_value = interrupt({"ticket_id": str(ticket_id), "reason": reason, "summary": summary})

    # On resume: operator reply arrived; incorporate it in the final answer.
    operator_reply = (resume_value or {}).get("reply", "")
    final_text = f"{_HUMAN_REPLY.get(language, _HUMAN_REPLY['pt'])}\n\n{operator_reply}"
    subtask: SubTask = {"id": "escalation", "agent": "escalation", "query": ""}
    result = make_result(subtask, "escalation", answer=final_text, confidence=1.0)
    return {
        "results": [result],
        "route_trace": ["escalation"],
        "final_response": final_text,
        "escalation": {
            "reason": reason,
            "status": "resolved",
            "ticket_id": str(ticket_id),
            "summary": summary,
            "pending_action": pending_action,
        },
    }
