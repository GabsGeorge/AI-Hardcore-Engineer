"""A flaky Support tool retries with backoff; persistent failures end with an honest error."""

import psycopg
import pytest
from langchain_core.runnables import RunnableConfig

from app.db.pool import Pool
from app.tools import support_tools

pytestmark = pytest.mark.req("REQ-SUP-03", "REQ-REL-01")

CONFIG: RunnableConfig = {
    "configurable": {"user_id": "cliente1988", "trace_id": "0" * 32, "language": "pt"}
}


async def test_transient_error_is_retried(db_pool: Pool, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    async def flaky(*args: object, **kwargs: object) -> list[dict[str, object]]:
        calls["n"] += 1
        if calls["n"] == 1:
            raise psycopg.OperationalError("connection reset")
        return []

    monkeypatch.setattr(support_tools.support_repo, "settlement_schedule", flaky)
    out = await support_tools.get_settlement_schedule(
        support_tools.GetSettlementScheduleInput(
            from_date=support_tools.date(2026, 10, 13),
            to_date=support_tools.date(2026, 10, 20),
        ),
        CONFIG,
    )
    assert out == []
    assert calls["n"] == 2


async def test_persistent_error_is_reported(db_pool: Pool, monkeypatch: pytest.MonkeyPatch) -> None:
    async def always_fails(*args: object, **kwargs: object) -> list[dict[str, object]]:
        raise psycopg.OperationalError("DB down")

    monkeypatch.setattr(support_tools.support_repo, "settlement_schedule", always_fails)
    with pytest.raises(psycopg.OperationalError):
        await support_tools.get_settlement_schedule(
            support_tools.GetSettlementScheduleInput(
                from_date=support_tools.date(2026, 10, 13),
                to_date=support_tools.date(2026, 10, 20),
            ),
            CONFIG,
        )
