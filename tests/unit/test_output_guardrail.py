"""Output guardrail unit tests (T117, T121, REQ-GR-04).

Each case drives ``output_guardrail`` with a hand-crafted state and inspects the state update:

1. a financial-promise reply is rewritten (flag ``output:rewritten``);
2. PII leaking into the final reply is re-masked (flag ``output:rewritten``);
3. a Knowledge-rooted reply that the grounding model marks as ungrounded is blocked;
4. the ``guardrail_flags`` the API consumes roundtrip through ``build_response`` as the
   contract literals ``pass | masked | blocked`` (input) and ``pass | rewritten | blocked``
   (output).
"""

from typing import Any
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.api.chat import build_response
from app.guardrails.output import output_guardrail
from tests.fakes import FakeLLM

pytestmark = pytest.mark.req("REQ-GR-04")


def _state(
    final: str,
    *,
    ai_id: str = "ai-1",
    language: str = "pt",
    results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """A minimal state carrying the fields `output_guardrail` reads."""
    return {
        "messages": [
            HumanMessage(content="pergunta do lojista", id="h-1"),
            AIMessage(content=final, id=ai_id),
        ],
        "final_response": final,
        "language": language,
        "results": results or [],
        "guardrail_flags": [],
        "route_trace": [],
    }


async def test_financial_promise_is_rewritten(fake_llm: FakeLLM) -> None:
    out = await output_guardrail(_state("Fique tranquilo, vou estornar a transação ainda hoje."))
    assert out["guardrail_flags"] == ["output:rewritten"]
    assert "vou estornar" not in out["final_response"].lower()
    # The replacement message keeps the original AIMessage id so the checkpoint stays clean.
    [ai] = out["messages"]
    assert isinstance(ai, AIMessage)
    assert ai.id == "ai-1"
    assert ai.content == out["final_response"]


async def test_financial_promise_in_english_is_rewritten(fake_llm: FakeLLM) -> None:
    out = await output_guardrail(
        _state("Don't worry, I will refund that charge for you right away.", language="en")
    )
    assert out["guardrail_flags"] == ["output:rewritten"]
    assert "i will refund" not in out["final_response"].lower()


async def test_pii_in_output_is_masked_and_flagged(fake_llm: FakeLLM) -> None:
    leaked = "Confirmando: o CPF 529.982.247-25 do portador foi registrado."
    out = await output_guardrail(_state(leaked))
    assert "[CPF]" in out["final_response"]
    assert "529.982" not in out["final_response"]
    assert out["guardrail_flags"] == ["output:rewritten"]
    [ai] = out["messages"]
    assert ai.id == "ai-1" and ai.content == out["final_response"]


async def test_knowledge_answer_without_grounding_is_blocked(fake_llm: FakeLLM) -> None:
    fake_llm.script(
        output_guard=[{"grounded": False, "reason": "claim not in sources"}],
    )
    results = [
        {
            "subtask_id": "s1",
            "agent": "knowledge",
            "answer": "A Get Smart custa R$ 100 por mês [1].",
            "confidence": 0.9,
            "sources": [
                {
                    "title": "Get Smart",
                    "url": "https://site.getnet.com.br/maquininhas/",
                    "kind": "kb",
                }
            ],
            "tools_used": [],
            "error": None,
        }
    ]
    state = _state("A Get Smart custa R$ 100 por mês [1].", results=results)
    out = await output_guardrail(state)
    assert out["guardrail_flags"] == ["output:blocked"]
    # The ungrounded claim is replaced by a safe wording; the leak never leaves the graph.
    assert "100" not in out["final_response"]
    [ai] = out["messages"]
    assert ai.id == "ai-1" and ai.content == out["final_response"]


async def test_knowledge_answer_with_grounding_passes(fake_llm: FakeLLM) -> None:
    fake_llm.script(output_guard=[{"grounded": True, "reason": "every claim cited"}])
    results = [
        {
            "subtask_id": "s1",
            "agent": "knowledge",
            "answer": "A Get Smart tem tela touch [1].",
            "confidence": 0.9,
            "sources": [
                {
                    "title": "Get Smart",
                    "url": "https://site.getnet.com.br/maquininhas/",
                    "kind": "kb",
                }
            ],
            "tools_used": [],
            "error": None,
        }
    ]
    out = await output_guardrail(_state("A Get Smart tem tela touch [1].", results=results))
    assert out["guardrail_flags"] == ["output:pass"]
    assert out["final_response"] == "A Get Smart tem tela touch [1]."


async def test_grounding_check_is_skipped_without_knowledge_sources(fake_llm: FakeLLM) -> None:
    # Support answer: no grounding call, so no scripted reply is needed.
    results = [
        {
            "subtask_id": "s1",
            "agent": "support",
            "answer": "Seu terminal está online.",
            "confidence": 0.9,
            "sources": [],
            "tools_used": [],
            "error": None,
        }
    ]
    out = await output_guardrail(_state("Seu terminal está online.", results=results))
    assert out["guardrail_flags"] == ["output:pass"]
    assert fake_llm.calls == []


# T121 — the flags written to state are exactly the contract literals the API consumes.


def test_contract_flags_roundtrip_through_build_response() -> None:
    cases = [
        (["input:pass", "output:pass"], ("pass", "pass")),
        (["input:masked", "output:pass"], ("masked", "pass")),
        (["input:blocked"], ("blocked", "pass")),
        (["input:pass", "output:rewritten"], ("pass", "rewritten")),
        (["input:pass", "output:blocked"], ("pass", "blocked")),
        (["input:masked", "output:rewritten"], ("masked", "rewritten")),
        # Extra non-contract flags carry hints to the Supervisor and must not reach the API.
        (["input:pass", "input:sensitive"], ("pass", "pass")),
        (["input:masked", "input:human_request"], ("masked", "pass")),
    ]
    for flags, (want_in, want_out) in cases:
        state = {
            "final_response": "ok",
            "route_trace": [],
            "results": [],
            "guardrail_flags": flags,
            "escalation": None,
        }
        response = build_response(state, uuid4(), "0" * 32)
        assert response.guardrails.input == want_in, (flags, want_in, response.guardrails.input)
        assert response.guardrails.output == want_out, (flags, want_out, response.guardrails.output)


def test_contract_literals_are_what_the_schema_declares() -> None:
    """A failure here means someone widened the GuardrailsResult literals in schemas.py."""
    from typing import get_args

    from app.api.schemas import GuardrailsResult

    assert set(get_args(GuardrailsResult.model_fields["input"].annotation)) == {
        "pass",
        "masked",
        "blocked",
    }
    assert set(get_args(GuardrailsResult.model_fields["output"].annotation)) == {
        "pass",
        "rewritten",
        "blocked",
    }
