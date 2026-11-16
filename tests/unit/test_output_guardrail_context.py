"""The grounding check must see what it needs to judge a reply: the merchant's question (is the
reply about the product or figure that was asked?) and the text of the passages (is each claim
in them?). Title and URL alone, or the reply alone, let invented answers through (REQ-GR-04)."""

from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.guardrails.output import output_guardrail
from tests.fakes import FakeLLM

pytestmark = pytest.mark.req("REQ-GR-04")

QUESTION = "Como contrato a Get Turbo X?"
PASSAGE = "Para contratar uma maquininha, informe CPF ou CNPJ e escolha o plano no app Getnet."


def _state(results: list[dict[str, Any]]) -> dict[str, Any]:
    reply = "Para contratar o Get Turbo X, cadastre-se no site da Getnet [1]."
    return {
        "messages": [HumanMessage(content=QUESTION, id="h-1"), AIMessage(content=reply, id="a-1")],
        "final_response": reply,
        "language": "pt",
        "results": results,
        "guardrail_flags": [],
        "route_trace": [],
    }


def _result(**extra: Any) -> dict[str, Any]:
    return {
        "subtask_id": "s1",
        "agent": "knowledge",
        "answer": "Para contratar o Get Turbo X, cadastre-se no site da Getnet [1].",
        "confidence": 0.77,
        "sources": [{"title": "Maquininhas", "url": "https://site.getnet.com.br/x/", "kind": "kb"}],
        "tools_used": [],
        "error": None,
        **extra,
    }


async def test_grounding_check_receives_the_question(fake_llm: FakeLLM) -> None:
    fake_llm.script(output_guard=[{"grounded": False, "reason": "entity not in sources"}])
    out = await output_guardrail(_state([_result()]))
    prompt = fake_llm.prompts("output_guard")
    assert QUESTION in prompt
    assert out["guardrail_flags"] == ["output:blocked"]


async def test_grounding_check_receives_the_passage_text(fake_llm: FakeLLM) -> None:
    fake_llm.script(output_guard=[{"grounded": True, "reason": "ok"}])
    await output_guardrail(_state([_result(evidence=[f"Maquininhas — Contratar\n{PASSAGE}"])]))
    assert PASSAGE in fake_llm.prompts("output_guard")


async def test_sources_without_evidence_still_list_title_and_url(fake_llm: FakeLLM) -> None:
    fake_llm.script(output_guard=[{"grounded": True, "reason": "ok"}])
    await output_guardrail(_state([_result()]))
    prompt = fake_llm.prompts("output_guard")
    assert "Maquininhas" in prompt and "https://site.getnet.com.br/x/" in prompt


async def test_high_confidence_with_citations_is_still_checked(fake_llm: FakeLLM) -> None:
    """No shortcut: confidence >= 0.70 plus [N] citations must not skip the grounding check."""
    fake_llm.script(output_guard=[{"grounded": False, "reason": "unsupported"}])
    out = await output_guardrail(_state([_result(confidence=0.95)]))
    assert out["guardrail_flags"] == ["output:blocked"]
    assert fake_llm.prompts("output_guard") != ""
