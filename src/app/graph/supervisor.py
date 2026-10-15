"""Supervisor = LLM planner + deterministic policy (research R-08, ADR 0001).

The LLM only produces the structured plan. Whether to synthesize, replan, escalate or degrade is
decided by `decide`, a pure function, so routing and termination are testable without a model.
"""

from typing import Any, Literal

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command, Send

from app.core.config import Settings, get_settings
from app.core.llm import get_model
from app.core.prompts import load_prompt
from app.graph.state import AgentResult, AgentState, PlanModel
from app.observability.metrics import ROUTE_TAKEN, TOKENS

Decision = Literal["synthesize", "replan", "escalate", "degrade"]
RECENT_MESSAGES = 6


def decide(results: list[AgentResult], attempts: int, settings: Settings) -> Decision:
    """Replan below CONFIDENCE_REPLAN or on errors; escalate on a result below
    CONFIDENCE_ESCALATE_HARD or when a replanned round is still not good enough."""
    if not results:
        return "degrade"
    ok = [r for r in results if not r["error"]]
    if len(ok) == len(results) and min(r["confidence"] for r in ok) >= settings.confidence_replan:
        return "synthesize"
    if ok and min(r["confidence"] for r in ok) < settings.confidence_escalate_hard:
        return "escalate"
    if attempts >= 1:
        return "escalate"
    return "replan"


def _planner_messages(state: AgentState) -> list[BaseMessage]:
    messages: list[BaseMessage] = [SystemMessage(content=load_prompt("supervisor"))]
    if state.get("summary"):
        messages.append(SystemMessage(content=f"Conversation summary: {state['summary']}"))
    # On a replan, tell the planner what did not work so it chooses a different strategy.
    prior = state.get("results") or []
    if prior:
        history = "; ".join(
            f"{r['agent']} confidence={r['confidence']:.2f}"
            + (f" error={r['error']}" if r["error"] else "")
            for r in prior
        )
        messages.append(SystemMessage(content=f"Previous attempts: {history}. Try another route."))
    messages.extend(state["messages"][-RECENT_MESSAGES:])
    return messages


async def plan_turn(state: AgentState) -> tuple[PlanModel | None, int]:
    """Chama o planner com um span dedicado anotado com a versão do prompt (REQ-OBS-02)."""
    from app.observability.tracing import get_tracer, set_prompt_version

    with get_tracer().start_as_current_span("supervisor.plan") as span:
        set_prompt_version(span, "supervisor")
        planner = get_model("supervisor").with_structured_output(PlanModel, include_raw=True)
        try:
            out = await planner.ainvoke(_planner_messages(state))
        except Exception as exc:
            span.record_exception(exc)
            return None, 0
        usage = getattr(out.get("raw"), "usage_metadata", None) or {}
        tokens = int(usage.get("total_tokens", 0))
        if tokens:
            TOKENS.labels("supervisor").inc(tokens)
            span.set_attribute("llm.tokens", tokens)
        parsed = out.get("parsed")
        if isinstance(parsed, PlanModel):
            span.set_attribute("plan.route", ",".join(parsed.route))
            span.set_attribute("plan.language", parsed.language or "")
            return parsed, tokens
        return None, tokens


def _dispatch(plan: PlanModel, update: dict[str, Any]) -> Command[Any]:
    if "escalation" in plan.route or plan.sensitive:
        ROUTE_TAKEN.labels("escalation").inc()
        if plan.sensitive:  # without this the escalation node files it as "human_request"
            update["escalation"] = {
                "reason": "sensitive_topic",
                "status": "awaiting_human",
                "ticket_id": None,
                "summary": "",
                "pending_action": None,
            }
        return Command(goto="escalation", update=update)
    sends = [
        Send(st.agent, {"subtask": st.model_dump(), "language": plan.language})
        for st in plan.subtasks
    ]
    for st in plan.subtasks:
        ROUTE_TAKEN.labels(st.agent).inc()
    return Command(goto=sends, update=update)


async def supervisor(state: AgentState, config: RunnableConfig) -> Command[Any]:
    settings = get_settings()
    step = state.get("step", 0) + 1
    update: dict[str, Any] = {"step": step, "route_trace": ["supervisor"]}
    spent = state.get("tokens_used", 0)
    if step > settings.max_steps or spent >= settings.token_budget_per_run:
        return Command(goto="degraded_response", update=update)

    if state.get("plan") is None:
        plan, tokens = await plan_turn(state)
        update["tokens_used"] = tokens
        if plan is None:
            return Command(goto="degraded_response", update=update)
        update |= {"plan": plan.model_dump(), "language": plan.language}
        if spent + tokens >= settings.token_budget_per_run:
            return Command(goto="degraded_response", update=update)
        return _dispatch(plan, update)

    results = state.get("results") or []
    attempts = state.get("attempts", 0)
    decision = decide(results, attempts, settings)
    if decision == "synthesize":
        return Command(goto="synthesize", update=update)
    if decision == "escalate":
        update["escalation"] = {
            "reason": "repeated_failures" if any(r["error"] for r in results) else "low_confidence",
            "status": "awaiting_human",
            "ticket_id": None,
            "summary": "",
            "pending_action": None,
        }
        return Command(goto="escalation", update=update)
    if decision == "replan":
        # Replan with a second strategy: give the planner the history of what did not work so
        # it chooses a different route (REQ-ORC-03). Results from the previous round are kept
        # on the state; the next round appends to it via the reducer.
        plan, tokens = await plan_turn(state)
        update["tokens_used"] = tokens
        update["attempts"] = attempts + 1
        if plan is None or spent + tokens >= settings.token_budget_per_run:
            return Command(goto="degraded_response", update=update)
        update |= {"plan": plan.model_dump(), "language": plan.language}
        return _dispatch(plan, update)
    return Command(goto="degraded_response", update=update)
