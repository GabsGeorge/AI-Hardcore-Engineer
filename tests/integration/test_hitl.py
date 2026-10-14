"""Human-in-the-loop: ticket + interrupt() + Command(resume) on the same thread (REQ-HITL)."""

from uuid import UUID

import httpx
import pytest

from app.api.auth import create_token
from app.db.pool import Pool
from tests.fakes import FakeLLM, make_plan
from tests.fixtures.kb import fresh_retriever  # noqa: F401


@pytest.fixture
def operator_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token('operador01', 'operator')}"}


@pytest.mark.req("REQ-HITL-01", "REQ-HITL-02")
async def test_explicit_human_request_pauses_with_a_ticket(
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    db_pool: Pool,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    fake_llm.script(
        supervisor=[make_plan("escalation", query="quero falar com um humano")],
        escalation=["Lojista quer falar com um atendente humano. Decida próximo passo."],
    )
    resp = await client.post(
        "/v1/chat",
        json={"message": "quero falar com um humano"},
        headers=auth_headers["cliente1988"],
    )
    body = resp.json()
    assert resp.status_code == 200
    assert body["handoff"]["status"] == "awaiting_human"
    assert body["handoff"]["ticket_id"] is not None
    async with db_pool.connection() as conn:
        row = await (
            await conn.execute(
                "SELECT user_id, reason, status FROM handoffs WHERE id = %s",
                (UUID(body["handoff"]["ticket_id"]),),
            )
        ).fetchone()
    assert row is not None
    assert row["user_id"] == "cliente1988"
    assert row["status"] == "awaiting_human"


@pytest.mark.req("REQ-HITL-03", "REQ-API-05")
async def test_operator_reply_resumes_and_merchant_sees_final_message(
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    db_pool: Pool,
    auth_headers: dict[str, dict[str, str]],
    operator_headers: dict[str, str],
) -> None:
    fake_llm.script(
        supervisor=[make_plan("escalation", query="quero um humano")],
        escalation=["Lojista pede atendente."],
    )
    first = (
        await client.post(
            "/v1/chat",
            json={"message": "quero falar com um atendente"},
            headers=auth_headers["cliente1988"],
        )
    ).json()
    ticket_id = first["handoff"]["ticket_id"]

    # The operator replies: resume runs with the ticket owner's identity (ADR 0005).
    reply = await client.post(
        f"/v1/handoffs/{ticket_id}/reply",
        json={"reply": "Estorno aprovado para a venda tx-123."},
        headers=operator_headers,
    )
    assert reply.status_code == 200
    assert reply.json()["status"] == "resolved"

    # The merchant reads the final message from the same conversation.
    conv = await client.get(
        f"/v1/conversations/{first['conversation_id']}", headers=auth_headers["cliente1988"]
    )
    assert conv.status_code == 200
    body = conv.json()
    assert body["handoff"]["status"] == "resolved"
    assert any("Estorno aprovado" in m["content"] for m in body["messages"])


@pytest.mark.req("REQ-SEC-06")
async def test_merchant_cannot_reply_handoff(
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    fake_llm.script(supervisor=[make_plan("escalation", query="humano")], escalation=["ok"])
    first = (
        await client.post(
            "/v1/chat",
            json={"message": "humano por favor"},
            headers=auth_headers["cliente1988"],
        )
    ).json()
    resp = await client.post(
        f"/v1/handoffs/{first['handoff']['ticket_id']}/reply",
        json={"reply": "hi"},
        headers=auth_headers["cliente1988"],
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden_role"


@pytest.mark.req("REQ-HITL-06")
async def test_handoff_queue_lists_only_awaiting_human(
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    auth_headers: dict[str, dict[str, str]],
    operator_headers: dict[str, str],
) -> None:
    fake_llm.script(
        supervisor=[make_plan("escalation", query="h")],
        escalation=["sum"],
    )
    await client.post(
        "/v1/chat", json={"message": "quero humano"}, headers=auth_headers["cliente1988"]
    )
    resp = await client.get(
        "/v1/handoffs", params={"status": "awaiting_human"}, headers=operator_headers
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items and all(item["status"] == "awaiting_human" for item in items)
