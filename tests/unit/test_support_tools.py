import asyncio
from datetime import date
from typing import Any

import pytest
from langchain_core.runnables import RunnableConfig

from app.agents.common import call_tool
from app.db import support_repo
from app.db.migrate import apply_seed
from app.db.pool import Pool
from app.tools.interfaces import ALLOWLIST, TIMEOUT_SECONDS, TOOL_OUTPUTS
from app.tools.support_tools import SUPPORT_TOOLS

pytestmark = pytest.mark.req("REQ-SUP-01")

REFERENCE = date(2026, 10, 13)


def _config(user_id: str = "cliente1988") -> RunnableConfig:
    return {"configurable": {"user_id": user_id, "thread_id": "t", "trace_id": "b" * 32}}


async def _call(name: str, args: dict[str, Any], user_id: str = "cliente1988") -> Any:
    return await call_tool("support", name, SUPPORT_TOOLS[name], args, _config(user_id))


@pytest.fixture
async def seeded(db_pool: Pool) -> Pool:
    await apply_seed(db_pool, REFERENCE)
    return db_pool


def test_registry_has_the_five_support_tools_with_2s_timeout() -> None:
    assert set(SUPPORT_TOOLS) == ALLOWLIST["support"] - {"search_knowledge_base"}
    assert {TIMEOUT_SECONDS[name] for name in SUPPORT_TOOLS} == {2.0}


async def test_settlement_schedule_groups_yesterdays_sales(seeded: Pool) -> None:
    out, record = await _call(
        "get_settlement_schedule", {"from_date": "2026-10-13", "to_date": "2026-10-13"}
    )
    assert record["status"] == "ok"
    assert all(isinstance(d, TOOL_OUTPUTS["get_settlement_schedule"]) for d in out)
    assert [d.model_dump() for d in out] == [
        {
            "expected_date": REFERENCE,
            "amount_cents": 46065,
            "status": "scheduled",
            "transaction_count": 3,
        }
    ]


@pytest.mark.parametrize(
    "args",
    [
        {"from_date": "2026-10-13", "to_date": "2026-10-12"},  # reversed
        {"from_date": "2026-01-01", "to_date": "2026-10-13"},  # > 90 days
        {"from_date": "ontem", "to_date": "2026-10-13"},
    ],
)
async def test_settlement_schedule_rejects_invalid_windows(
    seeded: Pool, args: dict[str, Any]
) -> None:
    out, record = await _call("get_settlement_schedule", args)
    assert out is None and record["status"] == "error"


async def test_empty_results_are_no_records(seeded: Pool) -> None:
    out, record = await _call(
        "get_settlement_schedule", {"from_date": "2025-01-01", "to_date": "2025-01-31"}
    )
    assert (out, record["status"]) == ([], "ok")
    out, record = await _call("get_recent_transactions", {"days": 7}, user_id="operador01")
    assert (out, record["status"]) == ([], "ok")
    out, record = await _call("diagnose_terminal", {"terminal_id": "NOPE"})
    assert (out, record["status"]) == ([], "ok")


async def test_diagnose_terminal_lists_terminals_with_checks(seeded: Pool) -> None:
    out, record = await _call("diagnose_terminal", {})
    assert record["status"] == "ok"
    assert all(isinstance(t, TOOL_OUTPUTS["diagnose_terminal"]) for t in out)
    assert [t.terminal_id for t in out] == ["T1988-01", "T1988-02"]
    offline = out[1]
    assert (offline.status, offline.last_error, offline.connectivity) == (
        "offline",
        "NO_SIGNAL",
        "chip_4g",
    )
    assert offline.suggested_checks
    one, _ = await _call("diagnose_terminal", {"terminal_id": "T1988-02"})
    assert [t.terminal_id for t in one] == ["T1988-02"]
    _, bad = await _call("diagnose_terminal", {"terminal_id": "x" * 65})
    assert bad["status"] == "error"


async def test_lookup_decline_code(seeded: Pool) -> None:
    out, record = await _call("lookup_decline_code", {"code": "51"})
    assert record["status"] == "ok"
    assert isinstance(out, TOOL_OUTPUTS["lookup_decline_code"])
    assert out.known and out.code == "51" and out.description and out.action
    unknown, _ = await _call("lookup_decline_code", {"code": "99"})
    assert unknown.model_dump() == {
        "code": "99",
        "known": False,
        "description": None,
        "action": None,
    }
    for code in ("", "12345"):
        _, bad = await _call("lookup_decline_code", {"code": code})
        assert bad["status"] == "error"


async def test_lookup_decline_code_follows_language(seeded: Pool) -> None:
    config = _config()
    config["configurable"]["language"] = "en"
    out, _ = await call_tool(
        "support",
        "lookup_decline_code",
        SUPPORT_TOOLS["lookup_decline_code"],
        {"code": "51"},
        config,
    )
    pt, _ = await _call("lookup_decline_code", {"code": "51"})
    assert out.description != pt.description
    assert "insufficient" in out.description.lower()


async def test_recent_transactions(seeded: Pool) -> None:
    out, record = await _call("get_recent_transactions", {"days": 30})
    assert record["status"] == "ok"
    assert all(isinstance(t, TOOL_OUTPUTS["get_recent_transactions"]) for t in out)
    assert [t.created_at for t in out] == sorted((t.created_at for t in out), reverse=True)
    assert len(out) == 6
    declined, _ = await _call("get_recent_transactions", {"days": 2, "status": "declined"})
    assert [(t.id, t.decline_code, t.amount_cents) for t in declined] == [
        ("tx-1988-004", "51", 12000)
    ]
    limited, _ = await _call("get_recent_transactions", {"days": 30, "limit": 2})
    assert len(limited) == 2
    window, _ = await _call("get_recent_transactions", {"days": 1})
    assert {t.created_at.date() for t in window} <= {date(2026, 10, 12), date(2026, 10, 13)}
    assert len(window) == 4


@pytest.mark.parametrize(
    "args",
    [
        {"days": 0},
        {"days": 31},
        {"days": 7, "limit": 0},
        {"days": 7, "limit": 51},
        {"days": 7, "status": "pending"},
    ],
)
async def test_recent_transactions_rejects_invalid_input(
    seeded: Pool, args: dict[str, Any]
) -> None:
    out, record = await _call("get_recent_transactions", args)
    assert out is None and record["status"] == "error"


async def test_customer_profile(seeded: Pool) -> None:
    out, record = await _call("get_customer_profile", {})
    assert record["status"] == "ok"
    assert isinstance(out, TOOL_OUTPUTS["get_customer_profile"])
    assert out.terminal_count == 2 and out.settlement_days == 1 and out.plan == "Get Smart"
    _, extra = await _call("get_customer_profile", {"anything": 1})
    assert extra["status"] == "error"
    # A user without a merchant profile (operator) gets an honest error, not someone else's data.
    _, none = await _call("get_customer_profile", {}, user_id="operador01")
    assert none["status"] == "error"


async def test_tool_respects_timeout(seeded: Pool, monkeypatch: pytest.MonkeyPatch) -> None:
    async def slow(*_: Any, **__: Any) -> Any:
        await asyncio.sleep(1)

    monkeypatch.setattr(support_repo, "customer_profile", slow)
    monkeypatch.setitem(TIMEOUT_SECONDS, "get_customer_profile", 0.05)
    out, record = await _call("get_customer_profile", {})
    assert out is None and record["status"] == "timeout"


async def test_tool_call_is_audited_with_the_caller(seeded: Pool) -> None:
    await _call("lookup_decline_code", {"code": "05"})
    async with seeded.connection() as conn:
        rows = await (
            await conn.execute("SELECT actor_id, action, target, outcome FROM audit_events")
        ).fetchall()
    assert rows == [
        {
            "actor_id": "cliente1988",
            "action": "tool_call",
            "target": "tool:lookup_decline_code",
            "outcome": "allowed",
        }
    ]
