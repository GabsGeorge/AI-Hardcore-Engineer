"""Knowledge specialist: answers about Getnet products with citations, or says it does not know."""

from typing import Any

from langchain_core.runnables import RunnableConfig

from app.agents.common import make_result
from app.graph.state import SpecialistInput


async def knowledge_node(state: SpecialistInput, config: RunnableConfig) -> dict[str, Any]:
    # STUB(T083): hybrid retrieval (BM25 + dense + RRF + rerank) and web search arrive in US1.
    result = make_result(state["subtask"], "knowledge", error="not_implemented")
    return {"results": [result], "route_trace": ["knowledge"]}
