import pytest

from app.db.pool import Pool
from app.rag import retriever
from tests.fakes import FakeLLM
from tests.fixtures.kb import (
    ADVANCE_EN,
    ADVANCE_EN_URL,
    add_document,
    answer,
    fresh_retriever,
    rewrite,
    run_knowledge,
)

__all__ = ["fresh_retriever"]
pytestmark = [pytest.mark.req("REQ-RAG-05"), pytest.mark.usefixtures("fresh_retriever")]

QUESTION = "Como funciona a antecipação de recebíveis?"


async def test_pt_question_retrieves_english_only_source(db_pool: Pool, fake_llm: FakeLLM) -> None:
    await add_document(db_pool, ADVANCE_EN_URL, "Receivables Advance", "en", ADVANCE_EN)
    # The Portuguese wording alone does not reach the English-only page...
    assert await retriever.search(QUESTION) == []

    fake_llm.script(
        knowledge_rewrite=[rewrite(("receivables advance fee", "en"))],
        knowledge=[answer("A antecipação permite receber as vendas antes do prazo [1].")],
    )
    out = await run_knowledge(QUESTION)
    result = out["results"][0]

    # ...but its English variant does, and the answer cites it.
    assert result["error"] is None
    assert [s["url"] for s in result["sources"]] == [ADVANCE_EN_URL]
    assert [t["name"] for t in result["tools_used"]] == ["search_knowledge_base"] * 2
    assert QUESTION in fake_llm.prompts("knowledge_rewrite")
    assert "Receivables advance lets merchants" in fake_llm.prompts("knowledge")
    assert result["confidence"] == pytest.approx(0.9)


async def test_rewrite_failure_falls_back_to_the_original_question(
    db_pool: Pool, fake_llm: FakeLLM
) -> None:
    await add_document(db_pool, ADVANCE_EN_URL, "Receivables Advance", "en", ADVANCE_EN)
    fake_llm.script(
        knowledge_rewrite=[ValueError("rewrite down")],
        knowledge=[answer("Receivables advance pays sales early [1].")],
    )
    out = await run_knowledge("receivables advance fee", language="en")
    result = out["results"][0]
    assert [t["name"] for t in result["tools_used"]] == ["search_knowledge_base"]
    assert [s["url"] for s in result["sources"]] == [ADVANCE_EN_URL]
    assert out["tokens_used"] == 240  # a failed rewrite still spent tokens
