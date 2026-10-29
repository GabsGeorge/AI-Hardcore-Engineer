"""Input guardrail node (REQ-GR-01, REQ-GR-02, REQ-GR-03).

Three barriers run in order: (1) PII masking (second barrier after `turn_input` in the API),
(2) regex heuristics that short-circuit the loudest attacks without an LLM call, and
(3) an LLM classifier (`input_guard`) with structured output. A blocking verdict sets
``guardrail_flags = ["input:blocked"]`` so ``route_after_input`` sends the turn to
``safe_response``. ``sensitive`` and ``human_request`` do not block (constitution IV): they are
appended as extra flags that the Supervisor can inspect without the API seeing them, since the
contract literals for the ``input`` field are only ``pass | masked | blocked``.
"""

import re
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.core.llm import get_model
from app.core.prompts import load_prompt
from app.graph.state import AgentState
from app.guardrails.pii import mask
from app.observability.metrics import GUARDRAIL_BLOCKS

Classification = Literal["safe", "injection", "out_of_scope", "sensitive", "human_request"]


class InputGuardResult(BaseModel):
    """Structured output of the ``input_guard`` role (REQ-GR-01, REQ-GR-03)."""

    classification: Classification
    reason: str = Field(default="", max_length=200)


# Heuristics (REQ-GR-01): short-circuit the loudest attacks without any LLM call. These cover
# ignore-the-rules, roleplay, prompt-extraction and the encoded-instructions families. The
# regexes stay generous on common PT/EN wordings; the LLM classifier handles the rest.
_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"ignor[ea]\s+(as\s+)?(regras|instru[cç][õo]es|todas|all|the|previous|prior|anterior)",
        re.IGNORECASE,
    ),
    re.compile(
        r"desconsidere\s+(as|todas|a|o)?\s*(regras|instru[cç][õo]es)",
        re.IGNORECASE,
    ),
    re.compile(
        r"esque[cç]a\s+(as|tudo|todas|everything|all)",
        re.IGNORECASE,
    ),
    re.compile(
        r"forget\s+(everything|all|the|prior|previous|above)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(finja|pretenda|pretend|act\s+as|aja\s+como|a\s+partir\s+de\s+agora\s+aja)\s+"
        r"(ser|que|a|an|o|um|uma|like|to\s+be)?",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(you\s+are\s+now|voc[eê]\s+(agora\s+)?[eé])\s+(dan|jailbroken|dev\s+mode|"
        r"a\s+jailbroken|a\s+system\s+administrator|the\s+system\s+administrator)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(mostre|revele|reveal|print|exiba|repita|repeat)\s+.{0,40}?"
        r"(system\s+prompt|prompt\s+do\s+sistema|instru[cç][õo]es\s+(do\s+sistema|internas)|"
        r"internal\s+(rules|instructions)|regras\s+(do\s+sistema|internas)|"
        r"your\s+(system\s+)?(prompt|instructions|rules)|suas\s+(instru[cç][õo]es|regras))",
        re.IGNORECASE,
    ),
    re.compile(
        r"nova\s+(regra|instru[cç][ãa]o)\s*(do\s+sistema)?\s*[:,]",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(decode|decodifique|converta|interpret|translate)\b.{0,40}?"
        r"(base64|rot13|hex|binary|binário|codificad|bin[áa]rio)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(base64|rot13)\s*[:,]|\b(em\s+rot13|em\s+base64|in\s+base64|in\s+rot13)\b",
        re.IGNORECASE,
    ),
    # IDOR por identificador de terceiro: menção explícita a dados "do cliente/usuário/lojista
    # CPF/CNPJ/e-mail" ou verbo de consulta + CPF/CNPJ. O guardrail de identidade (REQ-SEC-02)
    # já cobre `user_id` divergente no payload, mas o atacante pode tentar via linguagem
    # natural com um documento no texto.
    re.compile(
        r"\b(do|da|de|from|of|belonging\s+to|para)\s+"
        r"(cliente|usu[áa]rio|customer|merchant|user|conta|account|lojista|outro|other)\b"
        r".{0,40}?\b(cpf|cnpj|documento|document|e-?mail)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\b(mostre|exiba|liste|consulte|busque|traga|show|display|list|get|fetch|"
        r"retrieve|lookup|look\s+up|pull\s+up)\b.{0,80}?\b(cpf|cnpj)\b.{0,10}?\d{3}",
        re.IGNORECASE | re.DOTALL,
    ),
]


def _heuristic_hit(text: str) -> bool:
    return any(p.search(text) for p in _INJECTION_PATTERNS)


async def _classify(text: str) -> Classification | None:
    """One LLM call max. Fails open on error so the whole suite does not depend on the API."""
    try:
        model = get_model("input_guard").with_structured_output(InputGuardResult)
        result = await model.ainvoke(
            [
                SystemMessage(content=load_prompt("input_guard")),
                HumanMessage(content=text),
            ]
        )
    except Exception:
        return None
    return result.classification if isinstance(result, InputGuardResult) else None


async def input_guardrail(state: AgentState) -> dict[str, Any]:
    update: dict[str, Any] = {"route_trace": ["input_guardrail"]}
    found = list(state.get("input_pii") or [])

    last = state["messages"][-1] if state.get("messages") else None
    text = ""
    if isinstance(last, HumanMessage) and isinstance(last.content, str):
        masked, extra = mask(last.content)
        if extra:
            update["messages"] = [HumanMessage(content=masked, id=last.id)]
            found += extra
        text = masked
    mask_flag = "input:masked" if found else "input:pass"

    # Barrier 2: heuristics catch the loudest attacks with no LLM call at all.
    if text and _heuristic_hit(text):
        update["guardrail_flags"] = ["input:blocked"]
        GUARDRAIL_BLOCKS.labels("input", "heuristic").inc()
        return update

    # Barrier 3: structured-output classifier (bounded: one call max).
    classification = await _classify(text) if text else None
    if classification in ("injection", "out_of_scope"):
        update["guardrail_flags"] = ["input:blocked"]
        GUARDRAIL_BLOCKS.labels("input", classification).inc()
        return update

    flags = [mask_flag]
    if classification == "sensitive":
        flags.append("input:sensitive")
    elif classification == "human_request":
        flags.append("input:human_request")
    update["guardrail_flags"] = flags
    return update


def route_after_input(state: AgentState) -> Literal["safe_response", "summarize"]:
    return "safe_response" if "input:blocked" in state.get("guardrail_flags", []) else "summarize"
