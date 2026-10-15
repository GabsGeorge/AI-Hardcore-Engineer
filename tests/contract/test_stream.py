"""Contrato dos canais SSE (REQ-API-07, contracts/events.md)."""

from __future__ import annotations

import json

import httpx
import pytest

from app.db.pool import Pool
from tests.fakes import FakeLLM, make_plan
from tests.fixtures.kb import fresh_retriever, rewrite  # noqa: F401


def _parse_events(body: str) -> list[tuple[str, dict | str]]:
    """Mini parser SSE: faz pares (event, data) ignorando linhas em branco e pings."""
    out: list[tuple[str, dict | str]] = []
    event = None
    data_lines: list[str] = []
    for line in body.splitlines():
        if line.startswith(":"):  # heartbeat/comment
            continue
        if line == "":
            if event is not None and data_lines:
                raw = "\n".join(data_lines)
                try:
                    out.append((event, json.loads(raw)))
                except json.JSONDecodeError:
                    out.append((event, raw))
            event, data_lines = None, []
            continue
        if line.startswith("event:"):
            event = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:") :].strip())
    return out


@pytest.mark.req("REQ-API-07")
@pytest.mark.usefixtures("fresh_retriever")
async def test_chat_stream_emits_agent_step_and_done(
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    fake_llm.script(supervisor=[make_plan("knowledge")], knowledge_rewrite=[rewrite()])
    resp = await client.post(
        "/v1/chat/stream",
        json={"message": "O que é a Get Smart?"},
        headers=auth_headers["cliente1988"],
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    events = _parse_events(resp.text)
    names = [e for e, _ in events]
    assert "agent_step" in names
    assert names[-1] == "done"
    done_payload = events[-1][1]
    assert isinstance(done_payload, dict)
    assert "conversation_id" in done_payload
    assert "response" in done_payload


@pytest.mark.req("REQ-API-07")
@pytest.mark.usefixtures("fresh_retriever")
async def test_chat_stream_emits_handoff_when_escalation_opens(
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    fake_llm.script(
        supervisor=[make_plan("escalation", query="humano")],
        escalation=["Lojista pede atendente."],
    )
    resp = await client.post(
        "/v1/chat/stream",
        json={"message": "preciso de um humano"},
        headers=auth_headers["cliente1988"],
    )
    assert resp.status_code == 200
    events = _parse_events(resp.text)
    names = [e for e, _ in events]
    assert "handoff" in names
    handoff_payload = next(data for name, data in events if name == "handoff")
    assert isinstance(handoff_payload, dict)
    assert handoff_payload["status"] == "awaiting_human"
    assert handoff_payload["ticket_id"]


@pytest.mark.req("REQ-API-07")
@pytest.mark.usefixtures("fresh_retriever")
async def test_chat_stream_done_carries_the_full_route(
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    """Regression: merging per-node deltas by hand left `done.route` empty."""
    fake_llm.script(supervisor=[make_plan("knowledge")], knowledge_rewrite=[rewrite()])
    resp = await client.post(
        "/v1/chat/stream",
        json={"message": "O que é a Get Smart?"},
        headers=auth_headers["cliente1988"],
    )
    done = _parse_events(resp.text)[-1][1]
    assert isinstance(done, dict)
    assert "supervisor" in done["route"] and "knowledge" in done["route"]


@pytest.mark.req("REQ-SEC-07")
async def test_chat_stream_audits_foreign_user_id(
    client: httpx.AsyncClient,
    db_pool: Pool,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    resp = await client.post(
        "/v1/chat/stream",
        json={"message": "oi", "user_id": "cliente2024"},
        headers=auth_headers["cliente1988"],
    )
    assert resp.status_code == 403
    async with db_pool.connection() as conn:
        row = await (
            await conn.execute(
                "SELECT count(*)::int AS n FROM audit_events"
                " WHERE action = 'forbidden_user_mismatch' AND actor_id = 'cliente1988'"
            )
        ).fetchone()
    assert row is not None and row["n"] == 1
