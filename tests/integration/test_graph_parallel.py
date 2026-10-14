"""Compound question → fan-out to Knowledge and Support in one super-step (REQ-ORC-02)."""

from typing import Any

import pytest
from langchain_core.messages import HumanMessage
from langgraph.types import Command, Send

from app.graph.supervisor import supervisor
from tests.fakes import FakeLLM, make_plan

pytestmark = pytest.mark.req("REQ-ORC-02")

CONFIG = {"configurable": {"user_id": "cliente1988", "thread_id": "fanout", "trace_id": "0" * 32}}


def _state(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "messages": [
            HumanMessage(content="Minha máquina não conecta e como funciona a antecipação?")
        ],
        "summary": None,
        "language": None,
        "plan": None,
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
    base.update(overrides)
    return base


async def test_compound_plan_dispatches_both_specialists(fake_llm: FakeLLM) -> None:
    """Scenario 5 + 6: a plan with two subtasks fans out with Send so Knowledge and Support
    run in the same super-step; the reducer aggregates results."""
    fake_llm.script(supervisor=[make_plan("knowledge", "support", language="pt")])
    cmd = await supervisor(_state(), CONFIG)
    assert isinstance(cmd, Command)
    sends = cmd.goto
    assert isinstance(sends, list) and len(sends) == 2
    assert all(isinstance(s, Send) for s in sends)
    assert [s.node for s in sends] == ["knowledge", "support"]
    assert cmd.update["plan"]["route"] == ["knowledge", "support"]
