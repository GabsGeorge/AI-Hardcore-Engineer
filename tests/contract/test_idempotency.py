"""Idempotency-Key: mesma chave + corpo → mesma resposta sem reexecutar (REQ-API-06)."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from app.api.limits import idempotency_get_or_claim
from app.core.errors import AppError
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


@pytest.mark.req("REQ-API-06")
async def test_retry_while_first_request_runs_is_409_not_a_second_run(app: FastAPI) -> None:
    """Regression: the in-flight claim had response=None, so a concurrent retry ran the graph
    a second time — exactly what a client that timed out does."""
    await app.state.redis.flushdb()
    request = SimpleNamespace(app=app)
    body = {"message": "oi"}
    assert await idempotency_get_or_claim(request, "cliente1988", "k-1", body) is None  # type: ignore[arg-type]
    with pytest.raises(AppError) as exc:
        await idempotency_get_or_claim(request, "cliente1988", "k-1", body)  # type: ignore[arg-type]
    assert exc.value.code == "idempotency_in_progress"
