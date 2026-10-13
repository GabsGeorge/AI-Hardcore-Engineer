"""PII never reaches the model, the logs, the traces or the audit trail (REQ-GR-02)."""

import io
import json
import sys
from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from psycopg_pool import AsyncConnectionPool

from app.api.chat import graph_config
from app.observability.logging import configure_logging
from tests.fakes import FakeLLM

CARD = "4111 1111 1111 1111"
CPF = "529.982.247-25"
# Every rendering a leak could take: as typed, digits only, and the distinctive prefixes.
RAW_FORMS = [CARD, "4111111111111111", "4111-1111-1111-1111", CPF, "52998224725", "529.982.247"]


def _assert_clean(where: str, text: str) -> None:
    leaked = [form for form in RAW_FORMS if form in text]
    assert not leaked, f"raw PII {leaked} found in {where}"


@pytest.fixture
def log_stream(monkeypatch: pytest.MonkeyPatch) -> Iterator[io.StringIO]:
    """Rebinds the app's JSON logging (structlog and stdlib) to a buffer for one test.

    `configure_logging` binds `sys.stdout` when called (in the app lifespan), so capsys/capfd
    would not see it; calling it again with a patched stdout uses the real production pipeline.
    """
    buffer = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buffer)
    configure_logging()
    yield buffer
    monkeypatch.undo()
    configure_logging()


@pytest.fixture
def span_exporter() -> Iterator[InMemorySpanExporter]:
    """Attaches an in-memory exporter to the SDK provider installed by `configure_tracing`."""
    provider = trace.get_tracer_provider()
    assert isinstance(provider, TracerProvider), "configure_tracing did not install the SDK"
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    yield exporter
    exporter.shutdown()  # the processor stays registered but drops everything from now on


def _span_text(spans: tuple[ReadableSpan, ...]) -> str:
    parts: list[str] = []
    for span in spans:
        parts.append(span.name)
        parts.extend(f"{k}={v}" for k, v in (span.attributes or {}).items())
        for event in span.events:
            parts.append(event.name)
            parts.extend(f"{k}={v}" for k, v in (event.attributes or {}).items())
        parts.append(str(span.status.description or ""))
    return "\n".join(parts)


@pytest.mark.req("REQ-GR-02")
async def test_pii_never_reaches_llm_or_logs(
    app: FastAPI,
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    db_pool: AsyncConnectionPool,
    auth_headers: dict[str, dict[str, str]],
    log_stream: io.StringIO,
    span_exporter: InMemorySpanExporter,
) -> None:
    # Planner failure: the whole graph runs (guardrail, planner, degraded reply) without
    # depending on any specialist of another story.
    fake_llm.script(supervisor=[ValueError("down")])
    message = f"Meu CPF é {CPF} e o cartão {CARD}, por que a venda foi recusada?"
    resp = await client.post(
        "/v1/chat", json={"message": message}, headers=auth_headers["cliente1988"]
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["guardrails"]["input"] == "masked"

    # A second request puts the card in an audited field (divergent user_id → 403 + audit).
    denied = await client.post(
        "/v1/chat", json={"message": "oi", "user_id": CARD}, headers=auth_headers["cliente1988"]
    )
    assert denied.status_code == 403

    # 1. Prompts of every role: the model saw the masked tokens, never the raw values.
    prompts = fake_llm.prompts()
    assert "[CPF]" in prompts and "[CARTAO]" in prompts
    _assert_clean("LLM prompts", prompts)

    # 2. Structured logs (JSON on stdout).
    logs = log_stream.getvalue()
    records = [json.loads(line) for line in logs.splitlines() if line.strip()]
    assert any(r.get("event") == "request" for r in records), "no request log captured"
    _assert_clean("logs", logs)

    # 3. OpenTelemetry spans.
    spans = span_exporter.get_finished_spans()
    assert spans, "no span captured"
    _assert_clean("spans", _span_text(spans))

    # 4. Audit trail, every column.
    async with db_pool.connection() as conn:
        rows = await (await conn.execute("SELECT a::text AS row FROM audit_events a")).fetchall()
    assert rows, "no audit event captured"
    _assert_clean("audit_events", "\n".join(r["row"] for r in rows))
    assert any("[CARTAO]" in r["row"] for r in rows)

    # 5. Checkpointed state of the conversation and the reply itself.
    state = await app.state.graph.aget_state(
        graph_config("cliente1988", body["conversation_id"], body["trace_id"])
    )
    _assert_clean("checkpoint", " ".join(str(m.content) for m in state.values["messages"]))
    _assert_clean("response", resp.text + denied.text)
