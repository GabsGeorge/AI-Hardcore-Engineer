"""A claim that the product does NOT accept/offer something needs a source that says so; silence in
the sources is not evidence (REQ-GR-04). Enforced without the LLM, which lets it slip through."""

from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.guardrails.output import output_guardrail
from tests.fakes import FakeLLM

pytestmark = pytest.mark.req("REQ-GR-04")

QUESTION = "A Getnet aceita pagamento em criptomoedas na maquininha?"


def _state(reply: str, evidence: list[str], language: str = "pt") -> dict[str, Any]:
    result = {
        "subtask_id": "s1",
        "agent": "knowledge",
        "answer": reply,
        "confidence": 0.9,
        "sources": [{"title": "Maquininhas", "url": "https://site.getnet.com.br/m/", "kind": "kb"}],
        "tools_used": [],
        "error": None,
        "evidence": evidence,
    }
    return {
        "messages": [HumanMessage(content=QUESTION, id="h-1"), AIMessage(content=reply, id="a-1")],
        "final_response": reply,
        "language": language,
        "results": [result],
        "guardrail_flags": [],
        "route_trace": [],
    }


async def test_negative_claim_without_a_supporting_source_is_blocked(fake_llm: FakeLLM) -> None:
    # The grounding model would have said "grounded"; the deterministic check must win.
    fake_llm.script(output_guard=[{"grounded": True, "reason": "looks fine"}])
    out = await output_guardrail(
        _state(
            "A Getnet não aceita pagamento em criptomoedas na maquininha [1].",
            ["Maquininha — Pagamentos\nAceite Pix, crédito e débito na maquininha Getnet."],
        )
    )
    assert out["guardrail_flags"] == ["output:blocked"]
    assert "criptomoedas" not in out["final_response"]
    assert fake_llm.prompts("output_guard") == ""  # decided before any model call


async def test_negative_claim_backed_by_a_source_is_not_blocked(fake_llm: FakeLLM) -> None:
    fake_llm.script(output_guard=[{"grounded": True, "reason": "backed"}])
    out = await output_guardrail(
        _state(
            "A Get Clássica não aceita Pix [1].",
            ["Get Clássica\nA Get Clássica não aceita Pix; use a Get Smart para QR Code."],
        )
    )
    assert out["guardrail_flags"] == ["output:pass"]


async def test_negative_claim_in_english_is_blocked_too(fake_llm: FakeLLM) -> None:
    out = await output_guardrail(
        _state(
            "Getnet does not accept cryptocurrency payments [1].",
            ["Card machine\nAccept Pix, credit and debit."],
            language="en",
        )
    )
    assert out["guardrail_flags"] == ["output:blocked"]


async def test_product_level_negation_in_a_comparison_goes_to_the_grounding_model(
    fake_llm: FakeLLM,
) -> None:
    # "A Get Clássica não possui X" (sources attribute X to the Get Smart) is a comparison, not
    # a claim about what the company does not offer: the grounding model judges it.
    fake_llm.script(output_guard=[{"grounded": True, "reason": "backed by the comparison"}])
    out = await output_guardrail(
        _state(
            "A Get Clássica não possui o simulador de vendas; a Get Smart possui [1].",
            ["Get Smart\nSimulador de vendas disponível na Get Smart."],
        )
    )
    assert out["guardrail_flags"] == ["output:pass"]
    assert fake_llm.prompts("output_guard") != ""


async def test_reply_without_negation_goes_to_the_grounding_model(fake_llm: FakeLLM) -> None:
    fake_llm.script(output_guard=[{"grounded": True, "reason": "backed"}])
    out = await output_guardrail(
        _state("A Get Smart aceita Pix [1].", ["Get Smart\nA Get Smart aceita Pix por QR Code."])
    )
    assert out["guardrail_flags"] == ["output:pass"]
    assert fake_llm.prompts("output_guard") != ""
