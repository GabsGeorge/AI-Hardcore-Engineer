"""Supervisor replan policy: a weak first round triggers a second strategy (REQ-ORC-03)."""

from typing import Any

import pytest
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from app.graph.supervisor import supervisor
from tests.fakes import FakeLLM, make_plan

pytestmark = pytest.mark.req("REQ-ORC-03")

CONFIG = {"configurable": {"user_id": "cliente1988", "thread_id": "replan", "trace_id": "0" * 32}}


def _state(**overrides: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "messages": [HumanMessage(content="A Get Smart aceita contactless?")],
        "summary": None,
        "language": "pt",
        "plan": {"route": ["knowledge"]},
        "results": [],
        "attempts": 0,
        "step": 1,
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


async def test_low_confidence_triggers_a_second_plan(fake_llm: FakeLLM) -> None:
    # 0.55 is below CONFIDENCE_REPLAN (0.70) → the Supervisor re-plans with Support this time.
    fake_llm.script(supervisor=[make_plan("support")])
    cmd = await supervisor(_state(results=[_result(0.55)]), CONFIG)
    assert isinstance(cmd, Command)
    assert cmd.update["attempts"] == 1
    assert cmd.update["plan"]["route"] == ["support"]


async def test_good_confidence_does_not_replan(fake_llm: FakeLLM) -> None:
    # 0.75 is above the threshold → the Supervisor goes straight to synthesize.
    cmd = await supervisor(_state(results=[_result(0.75)]), CONFIG)
    assert cmd.goto == "synthesize"
    assert fake_llm.calls == []  # the planner was not called again


async def test_second_weak_round_escalates(fake_llm: FakeLLM) -> None:
    cmd = await supervisor(_state(results=[_result(0.5)], attempts=1), CONFIG)
    assert cmd.goto == "escalation"
    assert cmd.update["escalation"]["reason"] == "low_confidence"


async def test_error_without_results_degrades(fake_llm: FakeLLM) -> None:
    cmd = await supervisor(_state(results=[]), CONFIG)
    assert cmd.goto == "degraded_response"
