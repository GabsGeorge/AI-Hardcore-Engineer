"""Support specialist: resolves the authenticated merchant's case with their own data.

Tool loop of at most MAX_ROUNDS model calls. Every tool call goes through `call_tool` (Support
allowlist, validation, 2 s timeout, audit). Identity never reaches the prompt: tools read it from
`config` (ADR 0005). Confidence comes from tool outcomes only (research R-07)."""

import json
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from pydantic_core import to_jsonable_python

from app.agents.common import call_tool, make_result
from app.core.config import get_settings
from app.core.llm import get_model
from app.core.prompts import load_prompt
from app.graph.state import SpecialistInput, ToolCallRecord
from app.tools.interfaces import openai_tool_specs
from app.tools.knowledge_tools import search_knowledge_base
from app.tools.support_tools import SUPPORT_TOOLS, reference_date

# search_knowledge_base is on the Support allowlist (contracts/tools.md) and wired here so the
# model does not waste a round calling a tool that nobody runs (block review finding 4).
_SUPPORT_TOOLS = {**SUPPORT_TOOLS, "search_knowledge_base": search_knowledge_base}

MAX_ROUNDS = 4

NO_DATA = {
    "pt": "Não consegui consultar seus dados agora, então não posso responder com segurança. "
    "Tente novamente em instantes ou peça para falar com um atendente.",
    "en": "I couldn't retrieve your data right now, so I can't answer reliably. "
    "Please try again shortly or ask to talk to a human agent.",
}


def _confidence(records: list[ToolCallRecord]) -> float:
    ok = sum(r["status"] == "ok" for r in records)
    if not records or not ok:
        return 0.0
    return 1.0 if ok == len(records) else 0.5


async def support_node(state: SpecialistInput, config: RunnableConfig) -> dict[str, Any]:
    subtask, language = state["subtask"], state["language"]
    lang = "en" if language.startswith("en") else "pt"
    # Tools localise their texts to the subtask language; user_id stays as the API set it.
    tool_config: RunnableConfig = {
        **config,
        "configurable": {**config.get("configurable", {}), "language": lang},
    }
    plain = get_model("support")
    tooled = plain.bind_tools(openai_tool_specs("support"))
    messages: list[BaseMessage] = [
        SystemMessage(
            content=f"{load_prompt('support')}\nReference date (today): "
            f"{reference_date().isoformat()}.\nReply in the language with ISO code `{language}`."
        ),
        HumanMessage(content=subtask["query"]),
    ]
    records: list[ToolCallRecord] = []
    tokens, answer = 0, ""

    budget = get_settings().token_budget_per_run
    for round_index in range(MAX_ROUNDS):
        # Stop early if the per-run budget is spent; the supervisor still owns the final decision.
        if tokens >= budget:
            break
        # Last round: no tools, the model MUST answer with the data it already has.
        model = plain if round_index == MAX_ROUNDS - 1 else tooled
        try:
            reply = await model.ainvoke(messages)
        except Exception:
            result = make_result(subtask, "support", tools_used=records, error="model_error")
            return {"results": [result], "route_trace": ["support"], "tokens_used": tokens}
        tokens += int((getattr(reply, "usage_metadata", None) or {}).get("total_tokens", 0))
        if not reply.tool_calls:
            answer = str(reply.content)
            break
        messages.append(reply)
        for call in reply.tool_calls:
            impl = _SUPPORT_TOOLS.get(call["name"])
            output, record = await call_tool(
                "support", call["name"], impl, call["args"], tool_config
            )
            records.append(record)
            ok = record["status"] == "ok"
            content = to_jsonable_python(output) if ok else {"error": record["status"]}
            messages.append(
                ToolMessage(
                    content=json.dumps(content, ensure_ascii=False), tool_call_id=call["id"] or ""
                )
            )

    confidence = _confidence(records)
    if confidence == 0.0 or not answer.strip():
        # No data behind the answer: say so honestly instead of passing a guess along.
        answer, confidence = NO_DATA[lang], 0.0
    result = make_result(
        subtask, "support", answer=answer, confidence=confidence, tools_used=records
    )
    return {"results": [result], "route_trace": ["support"], "tokens_used": tokens}
