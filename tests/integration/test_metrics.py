"""Endpoint /metrics expõe o contrato de métricas da plataforma (REQ-OBS-03)."""

from __future__ import annotations

import httpx
import pytest

from tests.fakes import FakeLLM, make_plan
from tests.fixtures.kb import fresh_retriever, rewrite  # noqa: F401


@pytest.mark.req("REQ-OBS-03")
async def test_metrics_endpoint_is_prometheus_format(client: httpx.AsyncClient) -> None:
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    body = resp.text
    for name in (
        "getnet_http_requests_total",
        "getnet_http_request_duration_seconds",
        "getnet_route_total",
        "getnet_tokens_total",
        "getnet_tool_errors_total",
        "getnet_guardrail_blocks_total",
        "getnet_handoffs_total",
    ):
        assert name in body, f"métrica {name} ausente"


@pytest.mark.req("REQ-OBS-03")
@pytest.mark.usefixtures("fresh_retriever")
async def test_route_and_http_metrics_increment_on_a_chat_call(
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    fake_llm.script(supervisor=[make_plan("knowledge")], knowledge_rewrite=[rewrite()])
    chat_resp = await client.post(
        "/v1/chat",
        json={"message": "O que é a Get Smart?"},
        headers=auth_headers["cliente1988"],
    )
    assert chat_resp.status_code == 200
    metrics = (await client.get("/metrics")).text
    # Rota tomada pelo supervisor
    assert 'getnet_route_total{node="knowledge"}' in metrics
    # Requisição HTTP contabilizada (uma linha com status=200)
    assert 'getnet_http_requests_total{method="POST"' in metrics
    assert 'status="200"' in metrics


@pytest.mark.req("REQ-OBS-03")
@pytest.mark.usefixtures("fresh_retriever")
async def test_handoffs_metric_increments_on_escalation(
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    fake_llm.script(
        supervisor=[make_plan("escalation", query="humano")],
        escalation=["Lojista pede atendente."],
    )
    resp = await client.post(
        "/v1/chat",
        json={"message": "quero falar com um humano"},
        headers=auth_headers["cliente1988"],
    )
    assert resp.status_code == 200
    metrics = (await client.get("/metrics")).text
    assert 'getnet_handoffs_total{reason="human_request"}' in metrics
