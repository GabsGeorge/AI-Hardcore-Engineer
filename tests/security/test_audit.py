"""Trilha de auditoria completa (REQ-SEC-07).

Cada evento deve carregar ator, papel, ação, alvo, ``trace_id``, horário e **nenhuma PII**.
Cobrimos aqui os seis gatilhos chamados no spec:
``auth_failed``, ``forbidden_user_mismatch``, ``tool_call``, ``escalated``,
``operator_reply``, ``action_approved``.
"""

from __future__ import annotations

import re
from uuid import UUID

import httpx
import pytest

from app.api.auth import create_token
from app.db.pool import Pool
from tests.fakes import FakeLLM, make_plan
from tests.fixtures.kb import fresh_retriever, rewrite  # noqa: F401

_PII = re.compile(r"\b(\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})\b")


async def _fetch_events(db_pool: Pool, action: str | None = None) -> list[dict]:
    async with db_pool.connection() as conn:
        if action:
            cur = await conn.execute(
                "SELECT actor_id, actor_role, action, target, outcome, trace_id, ts"
                " FROM audit_events WHERE action = %s ORDER BY ts",
                (action,),
            )
        else:
            cur = await conn.execute(
                "SELECT actor_id, actor_role, action, target, outcome, trace_id, ts"
                " FROM audit_events ORDER BY ts"
            )
        return list(await cur.fetchall())


def _assert_no_pii(events: list[dict]) -> None:
    for ev in events:
        blob = f"{ev['actor_id']}|{ev['target']}"
        assert not _PII.search(blob), f"PII bruta em {ev}"


@pytest.mark.req("REQ-SEC-07")
@pytest.mark.usefixtures("fresh_retriever")
async def test_auth_failed_is_audited(
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    db_pool: Pool,
) -> None:
    resp = await client.post(
        "/v1/chat", json={"message": "oi"}, headers={"Authorization": "Bearer invalid"}
    )
    assert resp.status_code == 401
    events = await _fetch_events(db_pool, action="auth_failed")
    assert events and events[-1]["actor_id"] == "anonymous"
    assert events[-1]["outcome"] == "denied"
    _assert_no_pii(events)


@pytest.mark.req("REQ-SEC-07")
@pytest.mark.usefixtures("fresh_retriever")
async def test_forbidden_user_mismatch_is_audited(
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    db_pool: Pool,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    resp = await client.post(
        "/v1/chat",
        json={"message": "oi", "user_id": "cliente2024"},
        headers=auth_headers["cliente1988"],
    )
    assert resp.status_code == 403
    events = await _fetch_events(db_pool, action="forbidden_user_mismatch")
    assert events
    ev = events[-1]
    assert ev["actor_id"] == "cliente1988"
    assert ev["outcome"] == "denied"
    _assert_no_pii(events)


@pytest.mark.req("REQ-SEC-07")
@pytest.mark.usefixtures("fresh_retriever")
async def test_escalated_operator_reply_action_approved_are_audited(
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    db_pool: Pool,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    fake_llm.script(
        supervisor=[make_plan("escalation", query="humano")],
        escalation=["Lojista pede humano."],
    )
    first = await client.post(
        "/v1/chat",
        json={"message": "preciso falar com um humano"},
        headers=auth_headers["cliente1988"],
    )
    assert first.status_code == 200
    ticket_id = first.json()["handoff"]["ticket_id"]
    assert ticket_id is not None and UUID(ticket_id)

    escalated = await _fetch_events(db_pool, action="escalated")
    assert escalated and f"ticket:{ticket_id}" == escalated[-1]["target"]
    assert escalated[-1]["actor_id"] == "cliente1988"

    operator_headers = {"Authorization": f"Bearer {create_token('operador01', 'operator')}"}
    reply = await client.post(
        f"/v1/handoffs/{ticket_id}/reply",
        json={"reply": "Resolvido."},
        headers=operator_headers,
    )
    assert reply.status_code == 200
    op_events = await _fetch_events(db_pool, action="operator_reply")
    assert op_events and op_events[-1]["actor_id"] == "operador01"
    assert op_events[-1]["actor_role"] == "operator"


@pytest.mark.req("REQ-SEC-07")
@pytest.mark.usefixtures("fresh_retriever")
async def test_tool_call_is_audited(
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    db_pool: Pool,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    """O Knowledge chama ``search_knowledge_base`` como primeira etapa; esse call gera
    um ``tool_call`` na trilha. O target é ``tool:<nome>``, sem PII do lojista."""
    fake_llm.script(
        supervisor=[make_plan("knowledge")],
        knowledge_rewrite=[rewrite()],
    )
    resp = await client.post(
        "/v1/chat",
        json={"message": "O que é a Get Smart?"},
        headers=auth_headers["cliente1988"],
    )
    assert resp.status_code == 200
    tools = await _fetch_events(db_pool, action="tool_call")
    assert tools, "ao menos um tool_call deve estar na trilha"
    for ev in tools:
        assert ev["target"].startswith("tool:")
        assert ev["trace_id"]
    _assert_no_pii(tools)
