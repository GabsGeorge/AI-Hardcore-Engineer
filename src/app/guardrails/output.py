"""Output guardrail node (REQ-GR-04).

Three barriers run on the candidate reply, in order: (1) PII re-mask over ``final_response``
AND the last ``AIMessage`` (replaced with the SAME id so the checkpoint ends clean — block
review finding 4), (2) regex of financial promises → rewritten into a safe clarification, and
(3) grounding check (``output_guard`` LLM, structured output) when the turn carries a
Knowledge result with sources. Flags are set to the contract literals the API consumes:
``output:pass | output:rewritten | output:blocked``. The node runs after ``synthesize`` and
``degraded_response``; the ``safe_response`` branch skips it (see graph builder).
"""

import re
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.core.llm import get_model
from app.core.prompts import load_prompt
from app.graph.state import AgentState
from app.guardrails.pii import mask
from app.observability.logging import get_logger
from app.observability.metrics import GUARDRAIL_BLOCKS

_SAFE_REWRITE: dict[str, str] = {
    "pt": "Não posso prometer essa ação diretamente. Para avaliar o seu caso com segurança, "
    "posso transferir você para um atendente humano.",
    "en": "I can't promise that action directly. To review your case safely, I can transfer "
    "you to a human agent.",
}
_UNGROUNDED: dict[str, str] = {
    "pt": "Não encontrei base suficiente nas fontes consultadas para responder com confiança. "
    "Prefiro não arriscar; posso transferir você para um atendente humano.",
    "en": "I didn't find enough support in the sources I checked to answer confidently. "
    "I'd rather not guess; I can transfer you to a human agent.",
}


class GroundingResult(BaseModel):
    """Structured output of the ``output_guard`` role (REQ-GR-04, LLM09)."""

    grounded: bool
    reason: str = Field(default="", max_length=200)


# Financial-promise patterns (REQ-GR-04, LLM05): a reply that commits the system to a refund,
# chargeback approval or fee cancellation is rewritten before it leaves the graph.
_FINANCIAL_PROMISE = re.compile(
    r"("
    r"vou\s+estornar|j[áa]\s+estornei|estorno\s+(j[áa]\s+)?aprovad|"
    r"garanto\s+(o\s+|seu\s+)?(reembolso|estorno|chargeback)|"
    r"aprovo\s+(o\s+|seu\s+)?chargeback|"
    r"cancelo\s+(a\s+|sua\s+)?taxa|zerei\s+a\s+taxa|a\s+taxa\s+(agora\s+)?[eé]\s+zero|"
    r"i\s+will\s+refund|i\s+(have\s+)?refunded|i\s+approve\s+(your\s+)?chargeback"
    r")",
    re.IGNORECASE,
)


# A negative capability claim about the company itself ("A Getnet não aceita X", "Getnet does not
# offer X"). Silence in the sources does not prove it, and an LLM grounding check lets it through
# now and then, so this one is enforced deterministically: the passages must contain the same
# negation. Negations about one specific product ("a Get Clássica não possui X", common in a
# comparison where the sources attribute X to the other model) are left to the grounding model.
_NEGATIVE_CLAIM = re.compile(
    r"\bgetnet\b[^.!?\n]{0,40}?"
    r"(?P<negation>\bn[ãa]o\s+(?:aceita|oferece|possui|tem|permite|suporta|atende|disponibiliza)\b"
    r"|\b(?:does\s+not|doesn['’]t)\s+(?:accept|offer|have|support|allow)\b)",
    re.IGNORECASE,
)


def _has_unsupported_negative(reply: str, results: list[Any]) -> bool:
    evidence = " ".join(" ".join(r.get("evidence") or []) for r in results).lower()
    evidence = re.sub(r"\s+", " ", evidence)
    for claim in _NEGATIVE_CLAIM.finditer(reply):
        if re.sub(r"\s+", " ", claim.group("negation").lower()) not in evidence:
            return True
    return False


Flag = Literal["output:pass", "output:rewritten", "output:blocked"]


def _language(state: AgentState) -> str:
    lang = state.get("language")
    return lang if lang in ("pt", "en") else "pt"


def _sources_block(results: list[Any]) -> str:
    """Passages the answer model actually saw (``evidence``), numbered like its context. The
    grounding model needs the real text to judge each claim; title + url alone forces it to
    guess, which blocked correct answers and let unsupported ones through. Falls back to the
    bare source list only when a result carries no evidence."""
    lines: list[str] = []
    for r in results:
        evidence = r.get("evidence") or []
        if evidence:
            lines.extend(f"[{len(lines) + 1}] {text}" for text in evidence)
            continue
        for s in r.get("sources") or []:
            kind, title, url = s.get("kind", "kb"), s.get("title", ""), s.get("url", "")
            lines.append(f"[{len(lines) + 1}] ({kind}) {title} — {url}")
    return "\n\n".join(lines)


def _last_question(messages: list[Any]) -> str:
    """The merchant's latest message (already PII-masked by the input guardrail)."""
    human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    return human.content if human is not None and isinstance(human.content, str) else ""


async def _check_grounding(final: str, results: list[Any], question: str = "") -> bool | None:
    """``True``/``False`` from the model, ``None`` on error → fail-open (keep the reply).

    The question is part of the input: without it the checker can only confirm that each
    sentence appears in the sources, not that the reply is about what was asked (a named product
    or figure the sources never mention)."""
    try:
        model = get_model("output_guard").with_structured_output(GroundingResult)
        result = await model.ainvoke(
            [
                SystemMessage(content=load_prompt("grounding")),
                HumanMessage(
                    content=(
                        f"Question:\n{question}\n\nResponse:\n{final}\n\n"
                        f"Sources:\n{_sources_block(results)}"
                    )
                ),
            ]
        )
    except Exception:
        return None
    if not isinstance(result, GroundingResult):
        return None
    if not result.grounded:
        get_logger().info("output_grounding_verdict", trigger="model", reason=result.reason)
    return result.grounded


async def output_guardrail(state: AgentState) -> dict[str, Any]:
    update: dict[str, Any] = {"route_trace": ["output_guardrail"]}
    final = state.get("final_response") or ""
    messages = state.get("messages") or []
    last_ai: AIMessage | None = next(
        (m for m in reversed(messages) if isinstance(m, AIMessage)), None
    )

    # Barrier 1: PII re-mask over the final reply.
    masked_final, pii_found = mask(final)

    # Barrier 2: financial-promise rewrite. A reply authored by a human operator (HITL resume)
    # already carries authorized intent, so we skip this rewrite for the escalation route.
    language = _language(state)
    rewritten = False
    results = state.get("results") or []
    from_human_operator = any(r.get("agent") == "escalation" for r in results)
    if not from_human_operator and _FINANCIAL_PROMISE.search(masked_final):
        masked_final = _SAFE_REWRITE.get(language, _SAFE_REWRITE["pt"])
        rewritten = True

    # Barrier 3: grounding check sempre que a resposta vier do Knowledge COM fontes.
    # A checagem agora recebe o CONTEÚDO das passagens (não só título+URL), condição para
    # o modelo de guarda julgar se cada afirmação da resposta está de fato apoiada.
    knowledge_with_sources = [
        r
        for r in results
        if r.get("agent") == "knowledge" and not r.get("error") and r.get("sources")
    ]
    blocked = False
    if knowledge_with_sources and not rewritten:
        if _has_unsupported_negative(masked_final, knowledge_with_sources):
            get_logger().info("output_grounding_verdict", trigger="negative_claim")
            grounded: bool | None = False
        else:
            grounded = await _check_grounding(
                masked_final, knowledge_with_sources, _last_question(messages)
            )
        if grounded is False:
            masked_final = _UNGROUNDED.get(language, _UNGROUNDED["pt"])
            blocked = True

    flag: Flag
    if blocked:
        flag = "output:blocked"
        GUARDRAIL_BLOCKS.labels("output", "grounding").inc()
    elif rewritten or pii_found:
        flag = "output:rewritten"
        GUARDRAIL_BLOCKS.labels("output", "financial_promise" if rewritten else "pii").inc()
    else:
        flag = "output:pass"

    update["guardrail_flags"] = [flag]
    update["final_response"] = masked_final
    # Replace the last AIMessage with the SAME id so the checkpoint carries only the masked
    # version (block review finding 4): add_messages replaces by id and leaves nothing behind.
    if last_ai is not None:
        update["messages"] = [AIMessage(content=masked_final, id=last_ai.id)]
    return update
