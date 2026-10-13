"""Conversation ownership: a foreign or missing conversation is the same 404, and the graph thread
is always keyed by the token's user (REQ-MEM-01, REQ-SEC-02)."""

import uuid

import httpx
import pytest
from psycopg_pool import AsyncConnectionPool

from tests.fakes import SpyGraph

pytestmark = pytest.mark.req("REQ-MEM-01", "REQ-SEC-02")


async def _new_conversation(
    client: httpx.AsyncClient, headers: dict[str, str], **extra: str
) -> str:
    resp = await client.post("/v1/chat", json={"message": "oi", **extra}, headers=headers)
    assert resp.status_code == 200
    return str(resp.json()["conversation_id"])


async def test_foreign_and_missing_conversations_get_identical_404(
    client: httpx.AsyncClient, spy_graph: SpyGraph, auth_headers: dict[str, dict[str, str]]
) -> None:
    owned = await _new_conversation(client, auth_headers["cliente1988"])
    assert spy_graph.calls == 1

    candidates = {
        "foreign": owned,
        "foreign-uppercase": owned.upper(),  # same UUID, different spelling
        "foreign-no-hyphens": uuid.UUID(owned).hex,
        "missing-v4": str(uuid.uuid4()),
        "missing-nil": "00000000-0000-0000-0000-000000000000",
        "missing-max": "ffffffff-ffff-ffff-ffff-ffffffffffff",  # valid UUID, not version 4
        "missing-braced": "{12345678-1234-5678-1234-567812345678}",
    }
    responses = {
        name: await client.post(
            "/v1/chat",
            json={"message": "oi", "conversation_id": value},
            headers=auth_headers["cliente2024"],
        )
        for name, value in candidates.items()
    }

    statuses = {name: r.status_code for name, r in responses.items()}
    assert set(statuses.values()) == {404}, statuses
    errors = {name: r.json()["error"] for name, r in responses.items()}
    assert all(
        e == {"code": "not_found", "message": "Resource not found."} for e in errors.values()
    )
    # Same shape and headers: nothing but the per-request trace_id may differ.
    assert {tuple(sorted(r.json())) for r in responses.values()} == {("error", "trace_id")}
    assert {r.headers["content-type"] for r in responses.values()} == {"application/json"}
    assert len({len(r.content) for r in responses.values()}) == 1
    assert spy_graph.calls == 1  # no 404 ever reached the graph


async def test_thread_id_is_always_prefixed_by_the_token_user(
    client: httpx.AsyncClient,
    spy_graph: SpyGraph,
    db_pool: AsyncConnectionPool,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    a_conversation = await _new_conversation(client, auth_headers["cliente1988"])
    assert spy_graph.last_config["configurable"]["thread_id"] == f"cliente1988:{a_conversation}"

    # B starts a conversation with an explicit (matching) user_id: accepted, keyed by the token.
    b_conversation = await _new_conversation(
        client, auth_headers["cliente2024"], user_id="cliente2024"
    )
    configurable = spy_graph.last_config["configurable"]
    assert b_conversation != a_conversation
    assert configurable["user_id"] == "cliente2024"
    assert configurable["thread_id"] == f"cliente2024:{b_conversation}"

    # B continues the conversation, again with the matching user_id and a non-canonical spelling
    # of the id: the thread is the canonical `{token user}:{uuid}`.
    resp = await client.post(
        "/v1/chat",
        json={
            "message": "e agora?",
            "user_id": "cliente2024",
            "conversation_id": b_conversation.upper(),
        },
        headers=auth_headers["cliente2024"],
    )
    assert resp.status_code == 200
    assert resp.json()["conversation_id"] == b_conversation
    assert spy_graph.last_config["configurable"]["thread_id"] == f"cliente2024:{b_conversation}"
    calls_so_far = spy_graph.calls

    # B with A's conversation, even naming itself correctly in the body: 404 before the graph,
    # so A's owner never becomes a thread prefix for B.
    resp = await client.post(
        "/v1/chat",
        json={"message": "oi", "user_id": "cliente2024", "conversation_id": a_conversation},
        headers=auth_headers["cliente2024"],
    )
    assert resp.status_code == 404
    assert spy_graph.calls == calls_so_far

    # Every conversation row belongs to the user whose token created it.
    async with db_pool.connection() as conn:
        rows = await (
            await conn.execute("SELECT id::text AS id, user_id FROM conversations ORDER BY id")
        ).fetchall()
    assert {r["id"]: r["user_id"] for r in rows} == {
        a_conversation: "cliente1988",
        b_conversation: "cliente2024",
    }
