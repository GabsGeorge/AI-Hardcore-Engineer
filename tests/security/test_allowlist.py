from typing import Any

import pytest

from app.agents.common import call_tool
from app.db.pool import Pool

CONFIG = {"configurable": {"user_id": "cliente1988", "thread_id": "t", "trace_id": "a" * 32}}


@pytest.mark.req("REQ-ORC-05")
async def test_knowledge_cannot_call_support_tools(db_pool: Pool) -> None:
    executed: list[Any] = []

    async def impl(args: Any, config: Any) -> Any:
        executed.append(args)
        return []

    output, record = await call_tool(
        "knowledge",
        "get_settlement_schedule",
        impl,
        {"from_date": "2026-10-12", "to_date": "2026-10-20"},
        CONFIG,
    )
    assert output is None
    assert record == {"name": "get_settlement_schedule", "status": "denied", "latency_ms": 0}
    assert executed == []

    async with db_pool.connection() as conn:
        rows = await (
            await conn.execute(
                "SELECT actor_id, action, target, outcome, trace_id FROM audit_events"
            )
        ).fetchall()
    assert rows == [
        {
            "actor_id": "cliente1988",
            "action": "tool_denied",
            "target": "tool:get_settlement_schedule",
            "outcome": "denied",
            "trace_id": "a" * 32,
        }
    ]


@pytest.mark.req("REQ-ORC-05")
async def test_allowed_tool_runs_with_validated_input_and_is_audited(db_pool: Pool) -> None:
    async def impl(args: Any, config: Any) -> list[str]:
        assert args.query == "Get Smart"
        return ["hit"]

    output, record = await call_tool(
        "knowledge", "search_knowledge_base", impl, {"query": "Get Smart"}, CONFIG
    )
    assert output == ["hit"]
    assert record["status"] == "ok"


@pytest.mark.req("REQ-ORC-05")
async def test_invalid_tool_arguments_are_rejected_without_running(db_pool: Pool) -> None:
    async def impl(args: Any, config: Any) -> Any:
        raise AssertionError("must not run")

    output, record = await call_tool(
        "knowledge", "search_knowledge_base", impl, {"query": ""}, CONFIG
    )
    assert output is None
    assert record["status"] == "error"
