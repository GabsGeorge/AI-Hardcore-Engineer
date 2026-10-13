"""Knowledge specialist: answers about Getnet products with citations, or says it does not know.

1. `knowledge_rewrite` model → PT/EN query variants and whether the question is general.
2. `search_knowledge_base` for the question and each variant (hybrid retrieval, ADR 0003); hits
   are merged by chunk keeping the best reranked score.
3. Relevant hits → `knowledge` model answers from them. Otherwise a general question goes to
   `web_search`; anything else gets an honest "not found" without calling the model
   (REQ-RAG-07). Retrieved text is data inside `<untrusted_context>` (REQ-GR-05).
Confidence = min(self-assessment, objective signal) (research R-07).
"""

import asyncio
import re
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from app.agents.common import call_tool, make_result
from app.core.config import get_settings
from app.core.llm import get_model
from app.core.prompts import load_prompt
from app.graph.state import Source, SpecialistInput, ToolCallRecord
from app.rag.retriever import TOP_K, KbHit
from app.tools.interfaces import WebResult
from app.tools.knowledge_tools import search_knowledge_base, web_search

NOT_FOUND = {
    "pt": "Não encontrei essa informação nas fontes da Getnet que consultei, então prefiro não "
    "responder sem base. Você pode reformular a pergunta ou pedir para falar com um atendente.",
    "en": "I couldn't find this information in the Getnet sources I checked, so I'd rather not "
    "answer without a basis. You can rephrase the question or ask to talk to a human agent.",
}
UNAVAILABLE = {
    "pt": "Não consegui consultar as fontes de informação agora. Tente novamente em instantes "
    "ou peça para falar com um atendente.",
    "en": "I couldn't reach the information sources right now. Please try again shortly or ask "
    "to talk to a human agent.",
}
_REWRITE_MARKER = "<!-- query-rewrite -->"
_DELIMITER = re.compile(r"</?\s*untrusted_context[^>]*>", re.I)


class QueryVariant(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    lang: Literal["pt", "en"]


class QueryRewrite(BaseModel):
    """Structured output of the `knowledge_rewrite` role."""

    variants: list[QueryVariant] = Field(default_factory=list, max_length=3)
    general: bool = Field(
        default=False, description="public topic not about Getnet (weather, exchange rates)"
    )


class KnowledgeAnswer(BaseModel):
    """Structured output of the `knowledge` role."""

    answer: str = Field(min_length=1, max_length=4000)
    confidence: float = Field(ge=0, le=1)
    cited: list[int] = Field(default_factory=list, description="numbers of the items used")


def _prompts() -> tuple[str, str]:
    answer, rewrite = load_prompt("knowledge").split(_REWRITE_MARKER)
    return answer.strip(), rewrite.strip()


def _tokens(raw: Any) -> int:
    usage = getattr(raw, "usage_metadata", None) or {}
    return int(usage.get("total_tokens", 0))


async def _structured(
    role: str, schema: type[BaseModel], system: str, human: str
) -> tuple[Any, int]:
    """(parsed or None, tokens). A failing model is an outcome, never an exception."""
    model = get_model(role).with_structured_output(schema, include_raw=True)
    try:
        out = await model.ainvoke([SystemMessage(content=system), HumanMessage(content=human)])
    except Exception:
        return None, 0
    parsed = out.get("parsed")
    return (parsed if isinstance(parsed, schema) else None), _tokens(out.get("raw"))


async def _search(
    queries: list[tuple[str, str | None]], config: RunnableConfig
) -> tuple[list[KbHit], list[ToolCallRecord], bool]:
    """Best TOP_K hits over all queries, tool records, and whether any search worked."""
    calls = await asyncio.gather(
        *(
            call_tool(
                "knowledge",
                "search_knowledge_base",
                search_knowledge_base,
                {"query": q, "lang": lang},
                config,
            )
            for q, lang in queries
        )
    )
    best: dict[int, KbHit] = {}
    for output, _ in calls:
        for hit in output or []:
            if hit.chunk_id not in best or hit.score > best[hit.chunk_id].score:
                best[hit.chunk_id] = hit
    hits = sorted(best.values(), key=lambda h: h.score, reverse=True)[:TOP_K]
    return hits, [record for _, record in calls], any(r["status"] == "ok" for _, r in calls)


def _context(items: list[tuple[str, str]]) -> str:
    """Numbered items; delimiter tags are removed so retrieved text cannot close the block."""
    body = "\n\n".join(
        f"[{i}] {_DELIMITER.sub('', header)}\n{_DELIMITER.sub('', text)}"
        for i, (header, text) in enumerate(items, start=1)
    )
    return f"<untrusted_context>\n{body}\n</untrusted_context>"


def _cited(reply: KnowledgeAnswer, count: int) -> list[int]:
    """0-based indexes of the cited items; none valid → every item given to the model."""
    valid = sorted({n - 1 for n in reply.cited if 1 <= n <= count})
    return valid or list(range(count))


def _unique(sources: list[Source]) -> list[Source]:
    return list({s["url"]: s for s in sources}.values())


async def knowledge_node(state: SpecialistInput, config: RunnableConfig) -> dict[str, Any]:
    subtask = state["subtask"]
    question = subtask["query"]
    language = state["language"]
    fixed = language if language in NOT_FOUND else "en"
    answer_prompt, rewrite_prompt = _prompts()
    answer_system = answer_prompt.replace("{language}", language)

    rewrite, tokens = await _structured(
        "knowledge_rewrite", QueryRewrite, rewrite_prompt, f"Question:\n{question}"
    )
    rewrite = rewrite or QueryRewrite()
    queries = list(
        dict.fromkeys([(question[:500], None), *((v.query, v.lang) for v in rewrite.variants)])
    )
    hits, tools, kb_ok = await _search(queries, config)
    threshold = get_settings().rag_relevance_threshold
    relevant = [h for h in hits if h.score >= threshold]

    def done(
        answer: str = "",
        confidence: float = 0.0,
        sources: list[Source] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        result = make_result(
            subtask,
            "knowledge",
            answer=answer,
            confidence=confidence,
            sources=sources or [],
            tools_used=tools,
            error=error,
        )
        return {"results": [result], "route_trace": ["knowledge"], "tokens_used": tokens}

    if relevant:
        items = [(f"{h.title} — {h.section} ({h.url})", h.content) for h in relevant]
        reply, used = await _structured(
            "knowledge",
            KnowledgeAnswer,
            answer_system,
            f"Question:\n{question}\n\n{_context(items)}",
        )
        tokens += used
        if reply is None:
            return done(error="model_error")
        kb_sources: list[Source] = [
            {
                "title": relevant[i].title,
                "url": relevant[i].url,
                "kind": "kb",
                "retrieved_at": relevant[i].fetched_at.isoformat(),
            }
            for i in _cited(reply, len(relevant))
        ]
        return done(reply.answer, min(reply.confidence, relevant[0].score), _unique(kb_sources))

    if not rewrite.general:
        return done((NOT_FOUND if kb_ok else UNAVAILABLE)[fixed], hits[0].score if hits else 0.0)

    output, record = await call_tool(
        "knowledge", "web_search", web_search, {"query": question[:300]}, config
    )
    tools.append(record)
    if record["status"] != "ok":
        return done(UNAVAILABLE[fixed])
    results: list[WebResult] = output or []
    if not results:
        return done(NOT_FOUND[fixed])
    items = [
        (f"{r.title} ({r.url}), retrieved_at {r.retrieved_at.isoformat()}", r.snippet)
        for r in results
    ]
    reply, used = await _structured(
        "knowledge", KnowledgeAnswer, answer_system, f"Question:\n{question}\n\n{_context(items)}"
    )
    tokens += used
    if reply is None:
        return done(error="model_error")
    web_sources: list[Source] = [
        {
            "title": results[i].title,
            "url": results[i].url,
            "kind": "web",
            "retrieved_at": results[i].retrieved_at.isoformat(),
        }
        for i in _cited(reply, len(results))
    ]
    return done(reply.answer, min(reply.confidence, 1.0), _unique(web_sources))
