import json
from datetime import date
from typing import Any

import pytest
from langchain_core.runnables import RunnableConfig
from pydantic_core import to_jsonable_python

from app.agents.common import call_tool
from app.db.migrate import apply_seed
from app.db.pool import Pool
from app.tools.interfaces import GetCustomerProfileInput, openai_tool_specs
from app.tools.support_tools import SUPPORT_TOOLS

IDENTITY_WORDS = ("user", "merchant", "customer", "client", "owner", "account", "document")

# Every data tool with arguments wide enough to return everything the caller owns.
ALL_ARGS: dict[str, dict[str, Any]] = {
    "get_settlement_schedule": {"from_date": "2026-09-01", "to_date": "2026-11-30"},
    "diagnose_terminal": {},
    "lookup_decline_code": {"code": "05"},
    "get_recent_transactions": {"days": 30, "limit": 50},
    "get_customer_profile": {},
}

# Values that exist only in cliente2024's seed rows.
CLIENTE2024_MARKERS = ("2024", "77777", "44444", "22222", "75444", "43110", "Café Lua Cheia")


def _config(user_id: str) -> RunnableConfig:
    return {"configurable": {"user_id": user_id, "thread_id": "t", "trace_id": "c" * 32}}


def _properties(schema: dict[str, Any]) -> set[str]:
    """Every property name in a JSON schema, nested definitions included."""
    names = set(schema.get("properties", {}))
    for value in schema.values():
        if isinstance(value, dict):
            names |= _properties(value)
    return names


@pytest.mark.req("REQ-SEC-03")
def test_tool_schema_has_no_user_id() -> None:
    specs = openai_tool_specs("support")
    assert {s["function"]["name"] for s in specs} >= set(SUPPORT_TOOLS)
    for spec in specs:
        for prop in _properties(spec["function"]["parameters"]):
            assert not any(word in prop.lower() for word in IDENTITY_WORDS), (
                spec["function"]["name"],
                prop,
            )


@pytest.mark.req("REQ-SEC-03")
async def test_tool_uses_config_user(db_pool: Pool) -> None:
    await apply_seed(db_pool, date(2026, 10, 13))
    for name, args in ALL_ARGS.items():
        out, record = await call_tool(
            "support", name, SUPPORT_TOOLS[name], args, _config("cliente1988")
        )
        assert record["status"] == "ok", name
        dumped = json.dumps(to_jsonable_python(out), ensure_ascii=False)
        assert not any(marker in dumped for marker in CLIENTE2024_MARKERS), (name, dumped)

    # The other merchant's own data is reachable only with their own identity.
    out, _ = await call_tool(
        "support",
        "get_customer_profile",
        SUPPORT_TOOLS["get_customer_profile"],
        {},
        _config("cliente2024"),
    )
    assert out.trade_name == "Café Lua Cheia"


@pytest.mark.req("REQ-SEC-03")
async def test_foreign_terminal_returns_empty_list(db_pool: Pool) -> None:
    await apply_seed(db_pool, date(2026, 10, 13))
    out, record = await call_tool(
        "support",
        "diagnose_terminal",
        SUPPORT_TOOLS["diagnose_terminal"],
        {"terminal_id": "T2024-01"},
        _config("cliente1988"),
    )
    assert (out, record["status"]) == ([], "ok")


@pytest.mark.req("REQ-SEC-03")
@pytest.mark.parametrize("field", ["user_id", "merchant_id"])
async def test_identity_argument_from_the_model_is_rejected(db_pool: Pool, field: str) -> None:
    await apply_seed(db_pool, date(2026, 10, 13))
    out, record = await call_tool(
        "support",
        "get_recent_transactions",
        SUPPORT_TOOLS["get_recent_transactions"],
        {"days": 30, field: "cliente2024"},
        _config("cliente1988"),
    )
    assert out is None and record["status"] == "error"


@pytest.mark.req("REQ-SEC-03")
async def test_tool_without_server_identity_fails_closed(db_pool: Pool) -> None:
    await apply_seed(db_pool, date(2026, 10, 13))
    with pytest.raises(KeyError):
        await SUPPORT_TOOLS["get_customer_profile"](GetCustomerProfileInput(), {"configurable": {}})
