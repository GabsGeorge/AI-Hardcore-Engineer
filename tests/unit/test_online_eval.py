"""Avaliação online por amostragem (REQ-OBS-04).

Com ``EVAL_SAMPLE_RATE = 0.10``, cerca de 10% dos turnos vão para o juiz; os escores viram
observações do histograma Prometheus. Checamos a probabilidade (com uma margem ampla, para
não ficar frágil) e o caminho feliz com um juiz fake.
"""

from __future__ import annotations

import random

import httpx
import pytest

from app.core import llm
from app.core.config import get_settings
from app.ops.online_eval import schedule_score_turn, score_turn, should_sample
from tests.fakes import FakeLLM, make_plan
from tests.fixtures.kb import fresh_retriever, rewrite  # noqa: F401


@pytest.mark.req("REQ-OBS-04")
def test_should_sample_matches_configured_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "eval_sample_rate", 0.10)
    random.seed(0)
    hits = sum(1 for _ in range(10_000) if should_sample())
    assert 500 < hits < 1500, f"amostragem fora da margem: {hits}"


@pytest.mark.req("REQ-OBS-04")
async def test_score_turn_records_both_metrics(
    fake_llm: FakeLLM, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Chamada do juiz empacota duas observações no histograma — uma por métrica."""
    fake_llm.script(online_eval=[{"faithfulness": 0.9, "relevance": 0.85, "reason": "ok"}])
    recorded: list[tuple[str, float]] = []
    monkeypatch.setattr(
        "app.ops.online_eval._record",
        lambda metric, value, trace_id: recorded.append((metric, value)),
    )
    await score_turn("Qual a taxa?", "A taxa é X", "- fonte 1", trace_id="0" * 32)
    assert ("faithfulness", 0.9) in recorded
    assert ("relevance", 0.85) in recorded


@pytest.mark.req("REQ-OBS-04")
async def test_schedule_returns_none_when_not_sampled(
    monkeypatch: pytest.MonkeyPatch, fake_llm: FakeLLM
) -> None:
    monkeypatch.setattr("app.ops.online_eval.should_sample", lambda: False)
    task = schedule_score_turn("q", "a", "src", trace_id="0" * 32)
    assert task is None


@pytest.mark.req("REQ-OBS-04")
async def test_judge_failure_is_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Broken:
        def with_structured_output(self, _schema: object) -> _Broken:
            return self

        async def ainvoke(self, _msgs: object) -> None:
            raise RuntimeError("judge down")

    llm.set_overrides(model_factory=lambda _role: _Broken())
    try:
        # Não levanta e não grava.
        await score_turn("q", "a", "sources", trace_id="0" * 32)
    finally:
        llm.set_overrides(model_factory=None, embeddings=None)


@pytest.mark.req("REQ-OBS-04")
@pytest.mark.usefixtures("fresh_retriever")
async def test_chat_schedules_the_judge_with_the_masked_question(
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    """Regression: schedule_score_turn existed but nothing called it."""
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.api.chat.schedule_score_turn",
        lambda question, answer, sources, trace_id: calls.append((question, answer)),
    )
    fake_llm.script(supervisor=[make_plan("knowledge")], knowledge_rewrite=[rewrite()])
    resp = await client.post(
        "/v1/chat",
        json={"message": "meu email é fulano.silva@example.com, o que é a Get Smart?"},
        headers=auth_headers["cliente1988"],
    )
    assert resp.status_code == 200
    assert len(calls) == 1
    assert "fulano.silva@example.com" not in calls[0][0]
