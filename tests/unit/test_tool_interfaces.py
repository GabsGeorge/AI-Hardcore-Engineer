from datetime import date, timedelta

import pytest
from pydantic import BaseModel, ValidationError

from app.tools import interfaces as itf

pytestmark = pytest.mark.req("REQ-SEC-03", "REQ-ORC-05")

TOOLS = {
    "search_knowledge_base",
    "web_search",
    "get_settlement_schedule",
    "diagnose_terminal",
    "lookup_decline_code",
    "get_recent_transactions",
    "get_customer_profile",
    "create_ticket",
    "request_action_approval",
}
IDENTITY_FIELDS = {"user_id", "merchant_id", "customer_id", "owner", "sub", "account_id"}


def _fields(model: type[BaseModel]) -> set[str]:
    names = set(model.model_fields)
    for field in model.model_fields.values():
        ann = field.annotation
        if isinstance(ann, type) and issubclass(ann, BaseModel):
            names |= _fields(ann)
    return names


def test_all_contract_tools_have_input_and_output_models() -> None:
    assert set(itf.TOOL_INPUTS) == TOOLS
    assert set(itf.TOOL_OUTPUTS) == TOOLS
    assert set(itf.TIMEOUT_SECONDS) == TOOLS


def test_no_input_model_exposes_identity() -> None:
    for name, model in itf.TOOL_INPUTS.items():
        assert not (_fields(model) & IDENTITY_FIELDS), name
    for spec in [s for agent in itf.ALLOWLIST for s in itf.openai_tool_specs(agent)]:
        assert not (set(spec["function"]["parameters"].get("properties", {})) & IDENTITY_FIELDS)


def test_allowlists_match_contract() -> None:
    assert {
        "knowledge": {"search_knowledge_base", "web_search"},
        "support": {
            "get_settlement_schedule",
            "diagnose_terminal",
            "lookup_decline_code",
            "get_recent_transactions",
            "get_customer_profile",
            "search_knowledge_base",
        },
        "escalation": {"create_ticket", "request_action_approval"},
        "supervisor": set(),
    } == itf.ALLOWLIST


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("search_knowledge_base", {"query": ""}),
        ("search_knowledge_base", {"query": "x" * 501}),
        ("web_search", {"query": "x" * 301}),
        ("get_recent_transactions", {"days": 0, "limit": 10}),
        ("get_recent_transactions", {"days": 31, "limit": 10}),
        ("get_recent_transactions", {"days": 7, "limit": 51}),
        ("lookup_decline_code", {"code": ""}),
        ("lookup_decline_code", {"code": "12345"}),
        ("create_ticket", {"reason": "human_request", "summary": "x" * 1001}),
        ("request_action_approval", {"action": "refund_everything", "params": {}}),
    ],
)
def test_input_limits_from_contract(name: str, args: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        itf.TOOL_INPUTS[name].model_validate(args)


def test_settlement_window_is_limited_to_90_days() -> None:
    model = itf.TOOL_INPUTS["get_settlement_schedule"]
    start = date(2026, 1, 1)
    model.model_validate({"from_date": start, "to_date": start + timedelta(days=90)})
    with pytest.raises(ValidationError):
        model.model_validate({"from_date": start, "to_date": start + timedelta(days=91)})
    with pytest.raises(ValidationError):
        model.model_validate({"from_date": start, "to_date": start - timedelta(days=1)})
