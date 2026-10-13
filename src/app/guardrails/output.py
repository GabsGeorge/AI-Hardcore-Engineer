"""Output guardrail node. Runs before every reply leaves the graph (REQ-GR-04)."""

from typing import Any

from app.graph.state import AgentState


async def output_guardrail(state: AgentState) -> dict[str, Any]:
    # STUB(T120): PII re-masking, financial-promise rewrite and grounding check arrive in US6.
    return {"guardrail_flags": ["output:pass"], "route_trace": ["output_guardrail"]}
