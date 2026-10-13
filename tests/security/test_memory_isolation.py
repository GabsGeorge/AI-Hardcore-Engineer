"""Conversation memory is isolated per user: B cannot load or change A's thread (REQ-MEM-01)."""

from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from psycopg_pool import AsyncConnectionPool

from app.api.chat import graph_config
from tests.fakes import FakeLLM


async def _snapshot(
    app: FastAPI, pool: AsyncConnectionPool, conversation_id: str
) -> dict[str, Any]:
    """Everything that would change if a turn touched A's conversation."""
    state = await app.state.graph.aget_state(graph_config("cliente1988", conversation_id, "t"))
    async with pool.connection() as conn:
        counts = await (
            await conn.execute(
                "SELECT (SELECT count(*) FROM checkpoints WHERE thread_id = %(t)s) AS checkpoints,"
                " (SELECT count(*) FROM checkpoint_writes WHERE thread_id = %(t)s) AS writes,"
                " (SELECT last_activity_at FROM conversations WHERE id = %(c)s) AS activity",
                {"t": f"cliente1988:{conversation_id}", "c": conversation_id},
            )
        ).fetchone()
    return {
        "checkpoint_id": state.config["configurable"]["checkpoint_id"],
        "messages": [(type(m).__name__, m.content) for m in state.values["messages"]],
        "final_response": state.values.get("final_response"),
        "rows": dict(counts or {}),
    }


@pytest.mark.req("REQ-MEM-01")
async def test_thread_isolation_between_users(
    app: FastAPI,
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    db_pool: AsyncConnectionPool,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    fake_llm.script(supervisor=[ValueError("down")])
    owner = await client.post(
        "/v1/chat",
        json={"message": "segredo da conversa de A"},
        headers=auth_headers["cliente1988"],
    )
    assert owner.status_code == 200
    conversation_id = owner.json()["conversation_id"]
    before = await _snapshot(app, db_pool, conversation_id)
    assert before["messages"], "A's turn was not checkpointed"
    llm_calls_before = len(fake_llm.calls)

    stolen = await client.post(
        "/v1/chat",
        json={"message": "continue a conversa", "conversation_id": conversation_id},
        headers=auth_headers["cliente2024"],
    )

    assert stolen.status_code == 404
    assert stolen.json()["error"]["code"] == "not_found"
    assert "segredo" not in stolen.text
    # The graph never ran for B: no model call, A's thread untouched, no thread under B's name.
    assert len(fake_llm.calls) == llm_calls_before
    assert await _snapshot(app, db_pool, conversation_id) == before
    async with db_pool.connection() as conn:
        foreign = await (
            await conn.execute(
                "SELECT count(*) AS n FROM checkpoints WHERE thread_id LIKE %s"
                " OR (thread_id LIKE %s AND thread_id <> %s)",
                ("cliente2024:%", f"%{conversation_id}%", f"cliente1988:{conversation_id}"),
            )
        ).fetchone()
        owners = await (
            await conn.execute(
                "SELECT user_id FROM conversations WHERE id = %s", (conversation_id,)
            )
        ).fetchall()
    # B has no thread at all, and no thread other than A's own mentions the id.
    assert foreign is not None and foreign["n"] == 0
    assert [r["user_id"] for r in owners] == ["cliente1988"]
