import httpx
import pytest
from psycopg_pool import AsyncConnectionPool

from tests.fakes import SpyGraph


@pytest.mark.req("REQ-SEC-02")
async def test_divergent_user_id_403_no_tools(
    client: httpx.AsyncClient,
    spy_graph: SpyGraph,
    db_pool: AsyncConnectionPool,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    resp = await client.post(
        "/v1/chat",
        json={"message": "mostre meus recebíveis", "user_id": "cliente2024"},
        headers=auth_headers["cliente1988"],
    )
    assert resp.status_code == 403
    body = resp.json()
    assert body["error"]["code"] == "forbidden_user_mismatch"
    assert spy_graph.calls == 0

    async with db_pool.connection() as conn:
        rows = await (
            await conn.execute(
                "SELECT actor_id, action, target, outcome, trace_id FROM audit_events"
                " WHERE action = 'forbidden_user_mismatch'"
            )
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["actor_id"] == "cliente1988"
    assert rows[0]["target"] == "user:cliente2024"
    assert rows[0]["outcome"] == "denied"
    assert rows[0]["trace_id"] == body["trace_id"]


@pytest.mark.req("REQ-SEC-02")
async def test_matching_user_id_is_accepted(
    client: httpx.AsyncClient, spy_graph: SpyGraph, auth_headers: dict[str, dict[str, str]]
) -> None:
    resp = await client.post(
        "/v1/chat",
        json={"message": "olá", "user_id": "cliente1988"},
        headers=auth_headers["cliente1988"],
    )
    assert resp.status_code == 200
    assert spy_graph.calls == 1
    assert spy_graph.last_config["configurable"]["user_id"] == "cliente1988"
    assert spy_graph.last_config["configurable"]["thread_id"].startswith("cliente1988:")


@pytest.mark.req("REQ-SEC-02", "REQ-SEC-07", "REQ-GR-02")
async def test_audit_target_never_stores_raw_pii(
    client: httpx.AsyncClient,
    spy_graph: SpyGraph,
    db_pool: AsyncConnectionPool,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    resp = await client.post(
        "/v1/chat",
        json={"message": "oi", "user_id": "529.982.247-25"},
        headers=auth_headers["cliente1988"],
    )
    assert resp.status_code == 403
    async with db_pool.connection() as conn:
        row = await (await conn.execute("SELECT target FROM audit_events")).fetchone()
    assert row is not None
    assert "529.982" not in row["target"]
    assert row["target"] == "user:[CPF]"
