import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.graph.builder import build_graph

NODES = {
    "input_guardrail",
    "summarize",
    "supervisor",
    "knowledge",
    "support",
    "escalation",
    "synthesize",
    "degraded_response",
    "safe_response",
    "output_guardrail",
}
LLM_NODES = {"supervisor", "knowledge", "support", "escalation", "synthesize"}


def _edges() -> dict[str, set[str]]:
    graph = build_graph(InMemorySaver()).get_graph()
    out: dict[str, set[str]] = {}
    for edge in graph.edges:
        out.setdefault(edge.source, set()).add(edge.target)
    return out


@pytest.mark.req("REQ-ORC-01")
def test_all_nodes_are_registered() -> None:
    nodes = set(build_graph(InMemorySaver()).get_graph().nodes) - {"__start__", "__end__"}
    assert nodes == NODES


@pytest.mark.req("REQ-GR-02")
def test_input_guardrail_precedes_every_llm_node() -> None:
    edges = _edges()
    assert edges["__start__"] == {"input_guardrail"}
    # Walk from START without passing through the guardrail: no LLM node may be reachable.
    reachable, frontier = set(), ["__start__"]
    while frontier:
        node = frontier.pop()
        for nxt in edges.get(node, set()):
            if nxt != "input_guardrail" and nxt not in reachable:
                reachable.add(nxt)
                frontier.append(nxt)
    assert not (reachable & LLM_NODES)
