"""Spans do grafo carregam ``prompt.version`` e atributos de rota (REQ-OBS-02).

Instalamos um ``InMemorySpanExporter`` no provider do OTel durante o teste e disparamos uma
rodada do chat; o span ``supervisor.plan`` deve existir e carregar os atributos esperados.
"""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from tests.fakes import FakeLLM, make_plan
from tests.fixtures.kb import fresh_retriever, rewrite  # noqa: F401


@pytest.fixture
def spans() -> Iterator[InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = trace.get_tracer_provider()
    if isinstance(provider, TracerProvider):
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    yield exporter
    exporter.clear()


@pytest.mark.req("REQ-OBS-02")
@pytest.mark.usefixtures("fresh_retriever")
async def test_supervisor_plan_span_carries_prompt_version(
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    spans: InMemorySpanExporter,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    fake_llm.script(supervisor=[make_plan("knowledge")], knowledge_rewrite=[rewrite()])
    resp = await client.post(
        "/v1/chat",
        json={"message": "O que é a Get Smart?"},
        headers=auth_headers["cliente1988"],
    )
    assert resp.status_code == 200
    plan_spans = [s for s in spans.get_finished_spans() if s.name == "supervisor.plan"]
    assert plan_spans, "span supervisor.plan deveria existir"
    attrs = plan_spans[-1].attributes or {}
    assert attrs.get("prompt.name") == "supervisor"
    version = attrs.get("prompt.version")
    assert isinstance(version, str) and len(version) == 12
    assert attrs.get("plan.route") == "knowledge"
