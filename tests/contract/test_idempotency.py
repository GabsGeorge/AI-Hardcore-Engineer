"""Idempotency-Key: mesma chave + corpo → mesma resposta sem reexecutar (REQ-API-06)."""

from __future__ import annotations

import httpx
import pytest

from tests.fakes import FakeLLM, make_plan
from tests.fixtures.kb import fresh_retriever, rewrite  # noqa: F401


@pytest.mark.req("REQ-API-06")
@pytest.mark.usefixtures("fresh_retriever")
async def test_same_key_same_body_returns_cached_response(
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    fake_llm.script(supervisor=[make_plan("knowledge")], knowledge_rewrite=[rewrite()])
    headers = {**auth_headers["cliente1988"], "Idempotency-Key": "req-abc-123"}
    first = await client.post("/v1/chat", json={"message": "O que é a Get Smart?"}, headers=headers)
    assert first.status_code == 200
    body_a = first.json()
    # Mesmo payload + mesma chave → não roda o grafo de novo (scripts não repõem supervisor)
    second = await client.post(
        "/v1/chat", json={"message": "O que é a Get Smart?"}, headers=headers
    )
    assert second.status_code == 200
    assert second.json() == body_a


@pytest.mark.req("REQ-API-06")
@pytest.mark.usefixtures("fresh_retriever")
async def test_same_key_different_body_returns_409(
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    fake_llm.script(supervisor=[make_plan("knowledge")], knowledge_rewrite=[rewrite()])
    headers = {**auth_headers["cliente1988"], "Idempotency-Key": "req-xyz-999"}
    first = await client.post("/v1/chat", json={"message": "O que é a Get Smart?"}, headers=headers)
    assert first.status_code == 200
    conflict = await client.post(
        "/v1/chat", json={"message": "mensagem diferente"}, headers=headers
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"
