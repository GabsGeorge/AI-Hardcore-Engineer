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


Flag = Literal["output:pass", "output:rewritten", "output:blocked"]


def _language(state: AgentState) -> str:
    lang = state.get("language")
    return lang if lang in ("pt", "en") else "pt"


def _sources_block(results: list[Any]) -> str:
    lines = []
    for r in results:
        for s in r.get("sources") or []:
            lines.append(f"- [{s.get('kind', 'kb')}] {s.get('title', '')} — {s.get('url', '')}")
    return "\n".join(lines)


async def _check_grounding(final: str, results: list[Any]) -> bool | None:
    """``True``/``False`` from the model, ``None`` on error → fail-open (keep the reply)."""
    try:
        model = get_model("output_guard").with_structured_output(GroundingResult)
        result = await model.ainvoke(
            [
                SystemMessage(content=load_prompt("grounding")),
                HumanMessage(content=f"Response:\n{final}\n\nSources:\n{_sources_block(results)}"),
            ]
        )
    except Exception:
        return None
    return result.grounded if isinstance(result, GroundingResult) else None


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

    # Barrier 3: grounding check only when the reply came from Knowledge WITH sources.
    knowledge_with_sources = [
        r
        for r in results
        if r.get("agent") == "knowledge" and not r.get("error") and r.get("sources")
    ]
    blocked = False
    if knowledge_with_sources and not rewritten:
        grounded = await _check_grounding(masked_final, knowledge_with_sources)
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
