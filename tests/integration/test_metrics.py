"""Metrics contract (REQ-OBS-03). The exporter runs on an internal port, so tests read the
same registry it serves."""

from __future__ import annotations

import httpx
import pytest
from prometheus_client import generate_latest

from tests.fakes import FakeLLM, make_plan
from tests.fixtures.kb import fresh_retriever, rewrite  # noqa: F401


def _metrics() -> str:
    return generate_latest().decode()


@pytest.mark.req("REQ-OBS-03")
async def test_registry_exposes_the_platform_metrics(client: httpx.AsyncClient) -> None:
    body = _metrics()
    for name in (
        "getnet_http_requests_total",
        "getnet_http_request_duration_seconds",
        "getnet_route_total",
        "getnet_tokens_total",
        "getnet_tool_errors_total",
        "getnet_guardrail_blocks_total",
        "getnet_handoffs_total",
        "getnet_auth_failures_total",
    ):
        assert name in body, f"métrica {name} ausente"


@pytest.mark.req("REQ-OBS-03", "REQ-SEC-04")
async def test_metrics_are_not_served_on_the_public_api(client: httpx.AsyncClient) -> None:
    assert (await client.get("/metrics")).status_code == 404


@pytest.mark.req("REQ-OBS-03")
@pytest.mark.usefixtures("fresh_retriever")
async def test_route_and_http_metrics_increment_on_a_chat_call(
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    fake_llm.script(supervisor=[make_plan("knowledge")], knowledge_rewrite=[rewrite()])
    resp = await client.post(
        "/v1/chat", json={"message": "O que é a Get Smart?"}, headers=auth_headers["cliente1988"]
    )
    assert resp.status_code == 200
    metrics = _metrics()
    assert 'getnet_route_total{node="knowledge"}' in metrics
    assert 'getnet_http_requests_total{method="POST",route="/v1/chat",status="200"}' in metrics


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
    assert 'getnet_handoffs_total{reason="human_request"}' in _metrics()
