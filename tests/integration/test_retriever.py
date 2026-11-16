import pytest

from app.core.config import get_settings
from app.db.pool import Pool
from app.rag import retriever
from app.rag.chunking import passage
from tests.fakes import FakeLLM
from tests.fixtures.kb import (
    ADVANCE_EN_URL,
    MAQUININHAS,
    SMART_URL,
    add_document,
    fresh_retriever,
    seed_kb,
)

__all__ = ["fresh_retriever"]
pytestmark = [pytest.mark.req("REQ-RAG-04"), pytest.mark.usefixtures("fresh_retriever")]


async def test_hybrid_search_returns_reranked_hits_above_threshold(
    db_pool: Pool, fake_llm: FakeLLM
) -> None:
    await seed_kb(db_pool)
    hits = await retriever.search("get smart tela touch")
    assert hits and hits[0].url == SMART_URL and hits[0].section.endswith("Get Smart")
    assert hits[0].title == "Maquininhas Getnet"
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)
    assert all(get_settings().rag_relevance_threshold <= h.score <= 1 for h in hits)
    assert hits[0].fetched_at.isoformat().startswith("2026-10-01")


async def test_below_threshold_returns_nothing(db_pool: Pool, fake_llm: FakeLLM) -> None:
    await seed_kb(db_pool)
    assert await retriever.search("previsão do tempo amanhã") == []


async def test_top_5_after_rerank(db_pool: Pool, fake_llm: FakeLLM) -> None:
    sections = [(f"Pix > Parte {i}", f"pix na maquininha parte {i}") for i in range(8)]
    await add_document(db_pool, "https://site.getnet.com.br/pix/", "Pix", "pt", sections)
    hits = await retriever.search("pix maquininha")
    assert len(hits) == 5


async def test_lang_filter(db_pool: Pool, fake_llm: FakeLLM) -> None:
    await seed_kb(db_pool)
    hits = await retriever.search("receivables advance fee", lang="en")
    assert {h.url for h in hits} == {ADVANCE_EN_URL}
    assert await retriever.search("receivables advance fee", lang="pt") == []


async def test_dense_leg_uses_pgvector_cosine(db_pool: Pool, fake_llm: FakeLLM) -> None:
    ids = await add_document(db_pool, SMART_URL, "Maquininhas Getnet", "pt", MAQUININHAS)
    section, content = MAQUININHAS[1]
    exact = passage("Maquininhas Getnet", section, content)
    ranked = await retriever.dense_search(db_pool, exact, k=20)
    assert ranked[0] == ids[1] and set(ranked) == set(ids)


async def test_fusion_keeps_candidates_from_both_legs(
    db_pool: Pool, fake_llm: FakeLLM, monkeypatch: pytest.MonkeyPatch
) -> None:
    await seed_kb(db_pool)
    seen: list[list[list[int]]] = []
    original = retriever.rrf

    def spy(rankings: list[list[int]], k: int = retriever.RRF_K) -> list[tuple[int, float]]:
        seen.append(rankings)
        return original(rankings, k)

    monkeypatch.setattr(retriever, "rrf", spy)
    await retriever.search("código 51")
    bm25, dense = seen[0]
    assert bm25 == [3]  # exact term only in the decline-code chunk
    assert set(dense) == {1, 2, 3, 4}  # dense ranks every chunk of this tiny corpus


async def test_bm25_index_is_rebuilt_when_the_fingerprint_changes(
    db_pool: Pool, fake_llm: FakeLLM, monkeypatch: pytest.MonkeyPatch
) -> None:
    await seed_kb(db_pool)
    first = await retriever.bm25_index(db_pool)
    assert first is not None and sorted(first.ids) == [1, 2, 3, 4]

    new = await add_document(
        db_pool, "https://site.getnet.com.br/zebra/", "Zebra", "pt", [("Zebra", "zebra listrada")]
    )
    # Checked at most every REFRESH_SECONDS: the same index is served in the meantime.
    assert await retriever.bm25_index(db_pool) is first

    monkeypatch.setattr(retriever, "REFRESH_SECONDS", 0.0)
    rebuilt = await retriever.bm25_index(db_pool)
    assert rebuilt is not first and rebuilt is not None
    assert rebuilt.search("zebra", k=20) == new
    # Unchanged fingerprint → no rebuild.
    assert await retriever.bm25_index(db_pool) is rebuilt

    async with db_pool.connection() as conn:
        await conn.execute("DELETE FROM documents WHERE url = 'https://site.getnet.com.br/zebra/'")
    after_delete = await retriever.bm25_index(db_pool)
    assert after_delete is not rebuilt and after_delete is not None
    assert after_delete.search("zebra", k=20) == []


async def test_empty_knowledge_base(db_pool: Pool, fake_llm: FakeLLM) -> None:
    assert await retriever.bm25_index(db_pool) is None
    assert await retriever.search("get smart") == []
