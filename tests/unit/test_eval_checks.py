"""run_eval scoring rules: each declared expectation is checked against the API body."""

from __future__ import annotations

from typing import Any

import pytest

from evals.run_eval import check, load_scenarios


def _body(route: list[str], guard: str = "pass", handoff: str = "none") -> dict[str, Any]:
    return {
        "route": route,
        "guardrails": {"input": guard},
        "handoff": {"status": handoff},
        "tools_used": [{"name": "search_knowledge_base"}],
    }


@pytest.mark.req("REQ-OBS-06")
def test_route_must_contain_every_expected_node() -> None:
    assert check({"route": ["knowledge", "support"]}, _body(["knowledge"]))["route"] is False
    assert check({"route": ["knowledge"]}, _body(["supervisor", "knowledge"]))["route"] is True


@pytest.mark.req("REQ-OBS-06")
def test_safe_response_means_the_input_guardrail_blocked() -> None:
    assert check({"route": ["safe_response"]}, _body([], guard="blocked"))["route"] is True
    assert check({"route": ["safe_response"]}, _body(["knowledge"]))["route"] is False


@pytest.mark.req("REQ-OBS-06")
def test_every_golden_scenario_declares_a_route_or_pii_expectation() -> None:
    for sc in load_scenarios():
        assert "route" in sc["expected"] or sc["expected"].get("pii_masked"), sc["id"]
