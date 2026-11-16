from typing import Any

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.core.config import get_settings
from app.graph.builder import build_graph
from app.graph.supervisor import decide, supervisor
from tests.fakes import FakeLLM, Scripted, make_plan

pytestmark = pytest.mark.req("REQ-ORC-04")

CONFIG = {"configurable": {"user_id": "cliente1988", "thread_id": "budget", "trace_id": "0" * 32}}


def _state(**overrides: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "messages": [HumanMessage(content="oi")],
        "summary": None,
        "language": "pt",
        "plan": make_plan("knowledge"),
        "results": [],
        "attempts": 0,
        "step": 0,
        "tokens_used": 0,
        "route_trace": [],
        "escalation": None,
        "guardrail_flags": [],
        "final_response": None,
        "input_pii": [],
    }
    state.update(overrides)
    return state


def _result(confidence: float, error: str | None = None) -> dict[str, Any]:
    return {
        "subtask_id": "s1",
        "agent": "knowledge",
        "answer": "a",
        "confidence": confidence,
        "sources": [],
        "tools_used": [],
        "error": error,
    }


async def test_max_steps_degrades_gracefully(fake_llm: FakeLLM) -> None:
    max_steps = get_settings().max_steps
    cmd = await supervisor(_state(step=max_steps, results=[_result(0.9)]), CONFIG)
    assert cmd.goto == "degraded_response"
    assert cmd.update["step"] == max_steps + 1
    assert fake_llm.calls == []


async def test_token_budget(fake_llm: FakeLLM) -> None:
    budget = get_settings().token_budget_per_run
    cmd = await supervisor(_state(tokens_used=budget, results=[_result(0.9)]), CONFIG)
    assert cmd.goto == "degraded_response"


async def test_budget_blown_by_planning_stops_before_specialists(fake_llm: FakeLLM) -> None:
    budget = get_settings().token_budget_per_run
    fake_llm.script(supervisor=[Scripted(make_plan("knowledge"), tokens=budget + 1)])
    graph = build_graph(InMemorySaver())
    out = await graph.ainvoke(
        {"messages": [HumanMessage(content="oi")], "plan": None, "step": 0, "attempts": 0},
        {**CONFIG, "recursion_limit": 25},
    )
    assert "degraded_response" in out["route_trace"]
    assert "knowledge" not in out["route_trace"]
    assert out["final_response"]


def test_decision_policy_thresholds() -> None:
    s = get_settings()
    assert decide([_result(0.75)], attempts=0, settings=s) == "synthesize"
    assert decide([_result(0.55)], attempts=0, settings=s) == "replan"
    assert decide([_result(0.55)], attempts=1, settings=s) == "escalate"
    assert decide([_result(0.35)], attempts=0, settings=s) == "escalate"
    assert decide([_result(0.0, "timeout")], attempts=0, settings=s) == "replan"
    assert decide([_result(0.9), _result(0.0, "timeout")], attempts=1, settings=s) == "escalate"
    assert decide([], attempts=0, settings=s) == "degrade"
