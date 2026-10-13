"""Input guardrail node. Runs before every LLM node (REQ-GR-02)."""

from typing import Any, Literal

from langchain_core.messages import HumanMessage

from app.graph.state import AgentState
from app.guardrails.pii import mask


async def input_guardrail(state: AgentState) -> dict[str, Any]:
    # STUB(T119): injection heuristics, LLM classifier and out-of-scope refusal arrive in US6.
    # PII masking is already enforced here, as a second barrier after the API masking.
    update: dict[str, Any] = {"route_trace": ["input_guardrail"]}
    found = list(state.get("input_pii") or [])
    last = state["messages"][-1] if state.get("messages") else None
    if isinstance(last, HumanMessage) and isinstance(last.content, str):
        masked, extra = mask(last.content)
        if extra:
            update["messages"] = [HumanMessage(content=masked, id=last.id)]
            found += extra
    update["guardrail_flags"] = ["input:masked" if found else "input:pass"]
    return update


def route_after_input(state: AgentState) -> Literal["safe_response", "summarize"]:
    return "safe_response" if "input:blocked" in state.get("guardrail_flags", []) else "summarize"
