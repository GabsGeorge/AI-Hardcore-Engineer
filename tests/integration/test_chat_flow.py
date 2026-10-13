import re

import httpx
import pytest
from fastapi import FastAPI

from app.api.chat import graph_config
from app.db.pool import Pool
from tests.fakes import FakeLLM


@pytest.mark.req("REQ-API-01", "REQ-API-02")
async def test_chat_response_follows_contract_through_the_real_graph(
    client: httpx.AsyncClient, fake_llm: FakeLLM, auth_headers: dict[str, dict[str, str]]
) -> None:
    # Planner failure → honest degraded reply: exercises the whole graph without specialists.
    fake_llm.script(supervisor=[ValueError("planner unavailable")])
    resp = await client.post(
        "/v1/chat", json={"message": "O que é a Get Smart?"}, headers=auth_headers["cliente1988"]
    )
    assert resp.status_code == 200
    body = resp.json()
    assert re.fullmatch(r"[0-9a-f]{32}", body["trace_id"])
    assert body["route"] == [
        "input_guardrail",
        "supervisor",
        "degraded_response",
        "output_guardrail",
    ]
    assert body["handoff"] == {"status": "none", "ticket_id": None}
    assert body["guardrails"] == {"input": "pass", "output": "pass"}
    assert 0 <= body["confidence"] <= 1


@pytest.mark.req("REQ-API-02", "REQ-GR-02")
async def test_pii_is_masked_before_the_graph_and_never_checkpointed(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_pool: Pool,
    fake_llm: FakeLLM,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    fake_llm.script(supervisor=[ValueError("planner unavailable")])
    resp = await client.post(
        "/v1/chat",
        json={"message": "meu cpf é 529.982.247-25 e o cartão 4111 1111 1111 1111"},
        headers=auth_headers["cliente1988"],
    )
    body = resp.json()
    assert body["guardrails"]["input"] == "masked"
    assert "529.982.247-25" not in fake_llm.prompts()
    assert "4111 1111 1111 1111" not in fake_llm.prompts()

    state = await app.state.graph.aget_state(
        graph_config("cliente1988", body["conversation_id"], body["trace_id"])
    )
    stored = " ".join(str(m.content) for m in state.values["messages"])
    assert "[CPF]" in stored and "529.982" not in stored and "4111" not in stored
    async with db_pool.connection() as conn:
        raw = await (
            await conn.execute(
                "SELECT (SELECT count(*) FROM checkpoint_blobs"
                "         WHERE position('529.982' in encode(blob, 'escape')) > 0)"
                "     + (SELECT count(*) FROM checkpoint_writes"
                "         WHERE position('529.982' in encode(blob, 'escape')) > 0)"
                "     + (SELECT count(*) FROM checkpoints"
                "         WHERE position('529.982' in checkpoint::text) > 0) AS n"
            )
        ).fetchone()
    assert raw is not None and raw["n"] == 0


@pytest.mark.req("REQ-MEM-01")
async def test_second_turn_reuses_the_callers_conversation(
    client: httpx.AsyncClient, fake_llm: FakeLLM, auth_headers: dict[str, dict[str, str]]
) -> None:
    fake_llm.script(supervisor=[ValueError("down"), ValueError("down")])
    first = (
        await client.post("/v1/chat", json={"message": "oi"}, headers=auth_headers["cliente1988"])
    ).json()
    second = await client.post(
        "/v1/chat",
        json={"message": "e agora?", "conversation_id": first["conversation_id"]},
        headers=auth_headers["cliente1988"],
    )
    assert second.status_code == 200
    assert second.json()["conversation_id"] == first["conversation_id"]
    # Per-turn fields were reset: the second route is not appended to the first.
    assert second.json()["route"].count("input_guardrail") == 1


@pytest.mark.req("REQ-MEM-01", "REQ-SEC-02")
async def test_other_users_conversation_is_404_like_a_missing_one(
    client: httpx.AsyncClient, fake_llm: FakeLLM, auth_headers: dict[str, dict[str, str]]
) -> None:
    fake_llm.script(supervisor=[ValueError("down")])
    owner = (
        await client.post("/v1/chat", json={"message": "oi"}, headers=auth_headers["cliente1988"])
    ).json()
    stolen = await client.post(
        "/v1/chat",
        json={"message": "oi", "conversation_id": owner["conversation_id"]},
        headers=auth_headers["cliente2024"],
    )
    missing = await client.post(
        "/v1/chat",
        json={"message": "oi", "conversation_id": "00000000-0000-4000-8000-000000000000"},
        headers=auth_headers["cliente2024"],
    )
    assert stolen.status_code == missing.status_code == 404
    assert stolen.json()["error"] == missing.json()["error"]
