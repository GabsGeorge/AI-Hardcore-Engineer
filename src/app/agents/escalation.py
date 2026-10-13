"""Escalation specialist: ticket, pause with interrupt() and resume with the human reply."""

from typing import Any

from langchain_core.runnables import RunnableConfig

from app.agents.common import make_result
from app.graph.state import AgentState, SubTask


async def escalation_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    # STUB(T108): ticket, interrupt() and Command(resume=...) arrive in US5.
    subtask: SubTask = {"id": "escalation", "agent": "escalation", "query": ""}
    result = make_result(subtask, "escalation", error="not_implemented")
    return {"results": [result], "route_trace": ["escalation"]}
