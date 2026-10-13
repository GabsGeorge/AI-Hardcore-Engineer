"""Support specialist: resolves the authenticated merchant's case with their own data."""

from typing import Any

from langchain_core.runnables import RunnableConfig

from app.agents.common import make_result
from app.graph.state import SpecialistInput


async def support_node(state: SpecialistInput, config: RunnableConfig) -> dict[str, Any]:
    # STUB(T066): tool-driven answers over the merchant's data arrive in US2.
    result = make_result(state["subtask"], "support", error="not_implemented")
    return {"results": [result], "route_trace": ["support"]}
