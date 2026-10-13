from typing import Any

import pytest
from langchain_core.messages import HumanMessage
from langgraph.types import Command, Send

from app.graph.supervisor import supervisor
from tests.fakes import FakeLLM, make_plan

pytestmark = pytest.mark.req("REQ-ORC-01")

CONFIG = {"configurable": {"user_id": "cliente1988", "thread_id": "t", "trace_id": "0" * 32}}


def _state(**overrides: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "messages": [HumanMessage(content="Qual a diferença entre Get Clássica e Get Smart?")],
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
    state.update(overrides)
    return state


async def test_valid_plan_dispatches_each_subtask_with_send(fake_llm: FakeLLM) -> None:
    fake_llm.script(supervisor=[make_plan("knowledge", "support", language="en")])
    cmd = await supervisor(_state(), CONFIG)
    assert isinstance(cmd, Command)
    sends = cmd.goto
    assert isinstance(sends, list) and all(isinstance(s, Send) for s in sends)
    assert [s.node for s in sends] == ["knowledge", "support"]
    assert sends[0].arg["subtask"]["agent"] == "knowledge"
    assert sends[0].arg["language"] == "en"
    assert cmd.update["plan"]["route"] == ["knowledge", "support"]
    assert cmd.update["language"] == "en"
    assert cmd.update["step"] == 1
    assert cmd.update["tokens_used"] > 0


@pytest.mark.parametrize(
    "bad_plan",
    [
        {"route": ["knowledge"]},  # missing fields
        make_plan("knowledge") | {"route": ["support"]},  # route and subtasks disagree
        make_plan("knowledge") | {"subtasks": []},  # nothing to do
        make_plan("knowledge") | {"route": ["billing"]},  # unknown agent
        make_plan("knowledge") | {"confidence": 1.5},
        ValueError("model returned garbage"),
    ],
)
async def test_invalid_plan_degrades_and_never_executes(fake_llm: FakeLLM, bad_plan: Any) -> None:
    fake_llm.script(supervisor=[bad_plan])
    cmd = await supervisor(_state(), CONFIG)
    assert cmd.goto == "degraded_response"
    assert "plan" not in cmd.update or cmd.update["plan"] is None


async def test_human_request_or_sensitive_plan_goes_to_escalation(fake_llm: FakeLLM) -> None:
    fake_llm.script(supervisor=[make_plan("escalation"), make_plan("support", sensitive=True)])
    assert (await supervisor(_state(), CONFIG)).goto == "escalation"
    assert (await supervisor(_state(), CONFIG)).goto == "escalation"


async def test_planner_sees_summary_and_recent_messages_only_masked(fake_llm: FakeLLM) -> None:
    fake_llm.script(supervisor=[make_plan("knowledge")])
    await supervisor(_state(summary="Cliente perguntou sobre a Get Smart."), CONFIG)
    prompt = fake_llm.prompts("supervisor")
    assert "Cliente perguntou sobre a Get Smart." in prompt
    assert "Get Clássica" in prompt
    assert "cliente1988" not in prompt  # identity never reaches the model
