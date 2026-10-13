"""Terminal reply nodes: synthesize, degraded_response and safe_response (REQ-ORC-04/07)."""

import re
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.core.config import get_settings
from app.core.llm import get_model
from app.core.prompts import load_prompt
from app.graph.state import AgentState

DEGRADED = {
    "pt": "Não consegui concluir sua solicitação com segurança agora. Tente reformular a "
    "pergunta ou peça para falar com um atendente.",
    "en": "I couldn't complete your request reliably right now. Please rephrase the question "
    "or ask to talk to a human agent.",
}
SAFE = {
    "pt": "Não posso ajudar com esse pedido. Posso tirar dúvidas sobre produtos Getnet "
    "(maquininhas, Pix, antecipação, Link de Pagamento) e sobre seus recebíveis, terminais e "
    "transações.",
    "en": "I can't help with that request. I can answer questions about Getnet products "
    "(card machines, Pix, receivables advance, Payment Link) and about your settlements, "
    "terminals and transactions.",
}


def _as_data(text: str) -> str:
    """Answers may quote retrieved text: escaped so they can never form a delimiter tag."""
    return text.replace("<", "&lt;").replace(">", "&gt;")


_EN_HINTS = re.compile(
    r"\b(the|what|when|how|can|my|is|are|do|does|will|with|which|why|i|you|today)\b", re.I
)
_PT_HINTS = re.compile(
    r"\b(o|a|os|as|que|como|quando|meu|minha|é|está|posso|com|qual|hoje|não|para|de)\b", re.I
)


def guess_language(text: str) -> str:
    """Cheap fallback used before the planner has detected the language."""
    return "en" if len(_EN_HINTS.findall(text)) > len(_PT_HINTS.findall(text)) else "pt"


def _language(state: AgentState) -> str:
    if state.get("language"):
        return str(state["language"])
    last_user = next(
        (m for m in reversed(state.get("messages", [])) if isinstance(m, HumanMessage)), None
    )
    return guess_language(str(last_user.content)) if last_user else "pt"


def _reply(text: str, node: str, tokens: int = 0) -> dict[str, Any]:
    return {
        "final_response": text,
        "messages": [AIMessage(content=text)],
        "route_trace": [node],
        "tokens_used": tokens,
    }


async def synthesize(state: AgentState) -> dict[str, Any]:
    language = _language(state)
    answers = [r for r in state.get("results", []) if not r["error"] and r["answer"]]
    if not answers:
        return _reply(DEGRADED.get(language, DEGRADED["en"]), "synthesize")
    if len(answers) == 1:
        return _reply(answers[0]["answer"], "synthesize")
    if state.get("tokens_used", 0) >= get_settings().token_budget_per_run:
        # Over budget: no model call; the answers are joined as they are (REQ-ORC-04).
        return _reply("\n\n".join(r["answer"] for r in answers), "synthesize")
    question = next(
        (str(m.content) for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), ""
    )
    # Delimited as data: answers may quote retrieved web or knowledge-base text (REQ-GR-05).
    parts = "\n".join(
        f'<specialist_answer agent="{r["agent"]}">\n{_as_data(r["answer"])}\n</specialist_answer>'
        for r in answers
    )
    messages: list[BaseMessage] = [
        SystemMessage(content=load_prompt("synthesize").replace("{language}", language)),
        HumanMessage(content=f"Merchant question:\n{question}\n\nSpecialist answers:\n{parts}"),
    ]
    reply = await get_model("synthesize").ainvoke(messages)
    usage = getattr(reply, "usage_metadata", None) or {}
    return _reply(str(reply.content), "synthesize", int(usage.get("total_tokens", 0)))


async def degraded_response(state: AgentState) -> dict[str, Any]:
    language = _language(state)
    return _reply(DEGRADED.get(language, DEGRADED["en"]), "degraded_response")


async def safe_response(state: AgentState) -> dict[str, Any]:
    language = _language(state)
    return _reply(SAFE.get(language, SAFE["en"]), "safe_response")
