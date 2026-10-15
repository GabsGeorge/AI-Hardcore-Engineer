"""Avaliação online por amostragem com LLM-as-judge (REQ-OBS-04).

Para cada turno, com probabilidade ``EVAL_SAMPLE_RATE``, enviamos a resposta e as fontes para
um juiz (LLM separado) que emite dois escores:

- **faithfulness**: a resposta é sustentada pelas fontes?
- **relevance**: a resposta responde à pergunta?

A gravação é assíncrona (``asyncio.create_task``) e nunca bloqueia a resposta ao lojista. Erros
no juiz ou no sink de métricas são silenciosos — a avaliação é observação, não SLA.

Os escores vão para:
1. Métrica Prometheus ``getnet_online_eval_score`` com label ``metric``;
2. Log estruturado com ``trace_id`` para correlação com o span da requisição.
"""

from __future__ import annotations

import asyncio
import random
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from prometheus_client import Histogram
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.llm import get_model
from app.observability.logging import get_logger

ONLINE_EVAL_SCORE = Histogram(
    "getnet_online_eval_score",
    "LLM-as-judge: faithfulness e relevance amostrados em produção (0-1).",
    labelnames=("metric",),
    buckets=(0.0, 0.3, 0.5, 0.7, 0.8, 0.9, 1.0),
)


class JudgeVerdict(BaseModel):
    faithfulness: float = Field(ge=0.0, le=1.0)
    relevance: float = Field(ge=0.0, le=1.0)
    reason: str = Field(default="", max_length=200)


_JUDGE_PROMPT = (
    "You are an evaluator. Given a merchant question, a final answer and the sources used,"
    " score 0..1 for faithfulness (answer stays within sources) and relevance (answer actually"
    " addresses the question). Keep the reason under 200 chars."
)


def should_sample() -> bool:
    rate = get_settings().eval_sample_rate
    return rate > 0 and random.random() < rate  # noqa: S311 — amostragem, não cripto


async def _judge(question: str, answer: str, sources_block: str) -> JudgeVerdict | None:
    try:
        model = get_model("online_eval").with_structured_output(JudgeVerdict)
        result = await model.ainvoke(
            [
                SystemMessage(content=_JUDGE_PROMPT),
                HumanMessage(
                    content=(
                        f"Question:\n{question}\n\nAnswer:\n{answer}\n\nSources:\n{sources_block}"
                    )
                ),
            ]
        )
    except Exception:
        return None
    return result if isinstance(result, JudgeVerdict) else None


Metric = Literal["faithfulness", "relevance"]


def _record(metric: Metric, value: float, trace_id: str) -> None:
    ONLINE_EVAL_SCORE.labels(metric).observe(value)
    get_logger().info("online_eval", metric=metric, value=value, trace_id=trace_id)


async def score_turn(question: str, answer: str, sources_block: str, trace_id: str) -> None:
    """Avalia um turno **em segundo plano**. Nunca levanta."""
    verdict = await _judge(question, answer, sources_block)
    if verdict is None:
        return
    _record("faithfulness", verdict.faithfulness, trace_id)
    _record("relevance", verdict.relevance, trace_id)


def schedule_score_turn(
    question: str, answer: str, sources_block: str, trace_id: str
) -> asyncio.Task[None] | None:
    """Dispara o julgamento em uma task; devolve ``None`` quando o turno não foi amostrado."""
    if not should_sample():
        return None
    return asyncio.create_task(
        score_turn(question, answer, sources_block, trace_id), name="online-eval"
    )
