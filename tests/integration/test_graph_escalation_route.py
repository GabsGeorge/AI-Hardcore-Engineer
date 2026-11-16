"""A handoff turn must show `escalation` in its route even though the escalation node pauses on
interrupt() before it can append its own step (golden set sc-07, sc-08, sc-14)."""

from typing import Any

import pytest
from langchain_core.messages import HumanMessage

from app.graph.supervisor import supervisor
from tests.fakes import FakeLLM, make_plan

pytestmark = pytest.mark.req("REQ-HITL-01")

CONFIG = {"configurable": {"user_id": "cliente1988", "thread_id": "esc", "trace_id": "0" * 32}}


def _state() -> dict[str, Any]:
    return {
        "messages": [HumanMessage(content="Quero falar com um atendente humano agora.")],
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


async def test_explicit_human_request_records_escalation_in_the_route(fake_llm: FakeLLM) -> None:
    fake_llm.script(supervisor=[make_plan("escalation")])
    cmd = await supervisor(_state(), CONFIG)
    assert cmd.goto == "escalation"
    assert cmd.update["route_trace"] == ["supervisor", "escalation"]


async def test_sensitive_topic_records_escalation_in_the_route(fake_llm: FakeLLM) -> None:
    fake_llm.script(supervisor=[make_plan("knowledge", sensitive=True)])
    cmd = await supervisor(_state(), CONFIG)
    assert cmd.goto == "escalation"
    assert cmd.update["route_trace"] == ["supervisor", "escalation"]
    assert cmd.update["escalation"]["reason"] == "sensitive_topic"


async def test_normal_dispatch_does_not_claim_escalation(fake_llm: FakeLLM) -> None:
    fake_llm.script(supervisor=[make_plan("knowledge")])
    cmd = await supervisor(_state(), CONFIG)
    assert cmd.update["route_trace"] == ["supervisor"]
