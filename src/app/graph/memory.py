"""Conversation memory node: keeps `summary` + recent messages within budget (REQ-MEM-02)."""

from typing import Any

from app.graph.state import AgentState


async def summarize(state: AgentState) -> dict[str, Any]:
    # STUB(T125): summarise older messages above the configured limit (US7).
    return {}
