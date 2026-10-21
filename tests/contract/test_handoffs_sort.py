"""Fila ordenada por prioridade DESC e created_at ASC (T066 / FR-017)."""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from app.api.auth import create_token
from app.db.pool import Pool


@pytest.fixture
def operator_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token('operador01', 'operator')}"}


async def _insert_handoff(
    db_pool: Pool,
    *,
    user_id: str,
    reason: str,
    priority: str,
    created_offset: str,
) -> str:
    conversation_id = uuid4()
    ticket_id = uuid4()
    async with db_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO conversations (id, user_id) VALUES (%s, %s)",
            (conversation_id, user_id),
        )
        # The offset is a literal interval expression chosen by the test, not user input;
        # psycopg does not bind interval arithmetic, so we build the fragment with f-string.
        sql = f"INSERT INTO handoffs (id, conversation_id, user_id, reason, priority, summary, created_at, sla_due_at, expires_at) VALUES (%s, %s, %s, %s, %s, 'resumo', now() {created_offset}, now() + interval '15 min', now() + interval '24 hours')"  # noqa: E501, S608
        await conn.execute(sql, (ticket_id, conversation_id, user_id, reason, priority))
        await conn.execute(
            "UPDATE conversations SET handoff_status = 'awaiting_human' WHERE id = %s",
            (conversation_id,),
        )
    return str(ticket_id)


@pytest.mark.req("REQ-HITL-06")
async def test_queue_is_ordered_by_priority_then_oldest_first(
    client: httpx.AsyncClient, db_pool: Pool, operator_headers: dict[str, str]
) -> None:
    normal_old = await _insert_handoff(
        db_pool,
        user_id="cliente1988",
        reason="human_request",
        priority="normal",
        created_offset="- interval '5 minutes'",
    )
    high_newer = await _insert_handoff(
        db_pool,
        user_id="cliente2024",
        reason="sensitive_topic",
        priority="high",
        created_offset="- interval '1 minute'",
    )
    normal_newer = await _insert_handoff(
        db_pool,
        user_id="cliente1988",
        reason="human_request",
        priority="normal",
        created_offset="- interval '1 minute'",
    )

    resp = await client.get("/v1/handoffs?status=awaiting_human", headers=operator_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    ids = [_ticket_id(row) for row in items]
    assert ids[0] == high_newer  # high goes first
    assert ids.index(normal_old) < ids.index(normal_newer)  # within same priority, oldest first


def _ticket_id(row: dict) -> str:
    """Handoff model exposes the DB column as `ticket_id`; FastAPI falls back to `id` when the
    Pydantic alias is enabled without by_alias serialization. Either key is acceptable here;
    we just want the UUID string."""
    return row.get("ticket_id") or row["id"]


@pytest.mark.req("REQ-HITL-06")
async def test_queue_filter_by_status(
    client: httpx.AsyncClient, db_pool: Pool, operator_headers: dict[str, str]
) -> None:
    open_id = await _insert_handoff(
        db_pool,
        user_id="cliente1988",
        reason="human_request",
        priority="normal",
        created_offset="",
    )
    resolved_id = await _insert_handoff(
        db_pool,
        user_id="cliente1988",
        reason="human_request",
        priority="normal",
        created_offset="",
    )
    async with db_pool.connection() as conn:
        await conn.execute("UPDATE handoffs SET status = 'resolved' WHERE id = %s", (resolved_id,))

    awaiting = (
        await client.get("/v1/handoffs?status=awaiting_human", headers=operator_headers)
    ).json()["items"]
    assert [_ticket_id(row) for row in awaiting] == [open_id]
    resolved = (await client.get("/v1/handoffs?status=resolved", headers=operator_headers)).json()[
        "items"
    ]
    assert [_ticket_id(row) for row in resolved] == [resolved_id]
