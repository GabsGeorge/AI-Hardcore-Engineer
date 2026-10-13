import time
import uuid
from datetime import datetime
from typing import Any

import pytest
from langchain_core.runnables import RunnableConfig
from redis.asyncio import Redis

from app.agents import common, knowledge
from app.core.config import get_settings
from app.db.pool import Pool
from app.tools import knowledge_tools
from app.tools.interfaces import TIMEOUT_SECONDS, WebSearchInput
from tests.fakes import FakeLLM
from tests.fixtures.kb import answer, fresh_retriever, rewrite, run_knowledge

__all__ = ["fresh_retriever"]
pytestmark = pytest.mark.req("REQ-RAG-08")

CONFIG: RunnableConfig = {"configurable": {"user_id": "cliente1988", "trace_id": "0" * 32}}
RESULTS = [
    {"title": "Euro hoje", "href": "https://economia.example.com/euro", "body": "Euro a R$ 6,10."},
    {"title": "Sem link", "href": "javascript:alert(1)", "body": "descartado"},
    *[
        {"title": f"Resultado {i}", "href": f"https://news.example.com/{i}", "body": f"texto {i}"}
        for i in range(6)
    ],
]


class FakeDdgs:
    def __init__(self, results: list[dict[str, str]] = RESULTS, delay: float = 0.0) -> None:
        self.results, self.delay, self.calls = results, delay, 0

    def __call__(self, query: str, max_results: int) -> list[dict[str, str]]:
        self.calls += 1
        time.sleep(self.delay)
        return self.results[: max_results + 2]


def _unique(query: str) -> str:
    return f"{query} {uuid.uuid4().hex[:8]}"


async def _ttl(query: str) -> int:
    redis = Redis.from_url(get_settings().redis_url)
    try:
        return int(await redis.ttl(knowledge_tools.cache_key(query)))
    finally:
        await redis.aclose()


async def test_results_have_source_and_date_and_are_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeDdgs()
    monkeypatch.setattr(knowledge_tools, "ddgs_text", fake)
    query = _unique("cotação do euro hoje")
    first = await knowledge_tools.web_search(WebSearchInput(query=query), CONFIG)
    second = await knowledge_tools.web_search(WebSearchInput(query=query), CONFIG)

    assert fake.calls == 1
    assert first == second
    assert len(first) == 5  # at most 5, non-http links dropped
    assert first[0].url == "https://economia.example.com/euro"
    assert first[0].title == "Euro hoje" and first[0].snippet == "Euro a R$ 6,10."
    assert isinstance(first[0].retrieved_at, datetime) and first[0].retrieved_at.tzinfo
    assert all(r.url.startswith("https://") for r in first)


@pytest.mark.parametrize(
    ("query", "ttl"),
    [
        ("cotação do euro hoje", 15 * 60),
        ("dollar exchange rate", 15 * 60),
        ("previsão do tempo em São Paulo", 15 * 60),
        ("weather in Porto Alegre", 15 * 60),
        ("história do Pix no Brasil", 6 * 3600),
    ],
)
async def test_cache_ttl_depends_on_volatility(
    monkeypatch: pytest.MonkeyPatch, query: str, ttl: int
) -> None:
    monkeypatch.setattr(knowledge_tools, "ddgs_text", FakeDdgs())
    query = _unique(query)
    await knowledge_tools.web_search(WebSearchInput(query=query), CONFIG)
    assert ttl - 5 <= await _ttl(query) <= ttl


async def test_empty_results_are_not_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeDdgs(results=[])
    monkeypatch.setattr(knowledge_tools, "ddgs_text", fake)
    query = _unique("nada encontrado")
    assert await knowledge_tools.web_search(WebSearchInput(query=query), CONFIG) == []
    assert await knowledge_tools.web_search(WebSearchInput(query=query), CONFIG) == []
    assert fake.calls == 2


async def test_general_question_answers_with_web_source_and_date(
    db_pool: Pool, fake_llm: FakeLLM, fresh_retriever: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(knowledge_tools, "ddgs_text", FakeDdgs(results=RESULTS[:1]))
    fake_llm.script(
        knowledge_rewrite=[rewrite(general=True)],
        knowledge=[answer("O euro está a R$ 6,10 (Euro hoje, 13/10/2026) [1].", 0.8)],
    )
    out = await run_knowledge(_unique("Qual a cotação do euro hoje?"))
    result = out["results"][0]

    assert [t["name"] for t in result["tools_used"]] == ["search_knowledge_base", "web_search"]
    [source] = result["sources"]
    assert source["kind"] == "web" and source["url"] == "https://economia.example.com/euro"
    assert source["title"] == "Euro hoje"
    retrieved = datetime.fromisoformat(source["retrieved_at"])
    assert retrieved.tzinfo is not None
    assert result["confidence"] == pytest.approx(0.8)  # min(0.8, web results present → 1.0)
    prompt = fake_llm.prompts("knowledge")
    assert "Euro a R$ 6,10." in prompt and retrieved.date().isoformat() in prompt
    assert "<untrusted_context>" in prompt


async def test_web_timeout_is_an_honest_unavailability(
    db_pool: Pool, fake_llm: FakeLLM, fresh_retriever: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert TIMEOUT_SECONDS["web_search"] == 5.0
    monkeypatch.setitem(common.TIMEOUT_SECONDS, "web_search", 0.05)
    monkeypatch.setattr(knowledge_tools, "ddgs_text", FakeDdgs(delay=0.5))
    fake_llm.script(knowledge_rewrite=[rewrite(general=True)])
    out = await run_knowledge(_unique("Qual a cotação do dólar hoje?"))
    result = out["results"][0]

    assert [t["status"] for t in result["tools_used"]] == ["ok", "timeout"]
    assert result["answer"] == knowledge.UNAVAILABLE["pt"]
    assert result["sources"] == [] and result["confidence"] == 0.0
    assert fake_llm.prompts("knowledge") == ""  # nothing invented


async def test_general_question_without_web_results_says_so(
    db_pool: Pool, fake_llm: FakeLLM, fresh_retriever: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(knowledge_tools, "ddgs_text", FakeDdgs(results=[]))
    fake_llm.script(knowledge_rewrite=[rewrite(general=True)])
    out = await run_knowledge(_unique("What is the weather like?"), language="en")
    result: Any = out["results"][0]
    assert result["answer"] == knowledge.NOT_FOUND["en"]
    assert result["sources"] == [] and result["confidence"] == 0.0
