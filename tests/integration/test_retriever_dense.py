"""Default retrieval strategy: dense (ADR 0003). The fake embeddings are deterministic but not
semantic, so a query written exactly like a stored passage has similarity 1.0 with it and ~0 with
every other passage — enough to exercise the threshold, the per-page collapse and the ordering."""

from collections.abc import Iterator

import pytest

from app.core.config import get_settings
from app.db.pool import Pool
from app.rag import retriever
from app.rag.chunking import passage
from tests.fakes import FakeLLM
from tests.fixtures.kb import (
    ADVANCE_EN,
    ADVANCE_EN_URL,
    MAQUININHAS,
    SMART_URL,
    add_document,
    fresh_retriever,
    seed_kb,
)

__all__ = ["fresh_retriever"]
pytestmark = [pytest.mark.req("REQ-RAG-04"), pytest.mark.usefixtures("fresh_retriever")]


@pytest.fixture(autouse=True)
def dense_strategy(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("RAG_STRATEGY", "dense")
    get_settings.cache_clear()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()


def _query_like(title: str, section: str, content: str) -> str:
    return passage(title, section, content)


async def test_dense_is_the_default_strategy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RAG_STRATEGY")
    get_settings.cache_clear()
    assert get_settings().rag_strategy == "dense"


async def test_dense_returns_the_matching_page_with_its_similarity(
    db_pool: Pool, fake_llm: FakeLLM
) -> None:
    await seed_kb(db_pool)
    section, content = MAQUININHAS[0]
    hits = await retriever.search(_query_like("Maquininhas Getnet", section, content))
    assert [h.url for h in hits] == [SMART_URL]
    assert hits[0].score == pytest.approx(1.0, abs=1e-6)
    assert hits[0].section == section
    assert hits[0].fetched_at.isoformat().startswith("2026-10-01")


async def test_dense_threshold_drops_unrelated_passages(db_pool: Pool, fake_llm: FakeLLM) -> None:
    await seed_kb(db_pool)
    assert await retriever.search("previsão do tempo amanhã em Porto Alegre") == []


async def test_dense_threshold_is_the_calibrated_cosine_cutoff() -> None:
    assert get_settings().rag_dense_threshold == pytest.approx(0.40)
    assert get_settings().rag_dense_strong == pytest.approx(0.70)


@pytest.mark.parametrize(
    ("cosine", "expected"),
    [
        (0.40, 0.70),  # at the gate: retrieval is not the limiting factor (= replan threshold)
        (0.55, 0.85),  # halfway between gate and strong
        (0.70, 1.0),  # strong match
        (0.95, 1.0),  # beyond strong: capped
        (0.30, 0.70),  # below the gate never reaches here, but must not go under at_gate
    ],
)
def test_dense_relevance_maps_cosine_onto_the_confidence_scale(
    cosine: float, expected: float
) -> None:
    assert retriever.dense_relevance(cosine, 0.40, 0.70, 0.70) == pytest.approx(expected)


def test_dense_relevance_with_degenerate_range_is_one() -> None:
    assert retriever.dense_relevance(0.5, 0.7, 0.7, 0.7) == 1.0


async def test_dense_keeps_one_passage_per_page(
    db_pool: Pool, fake_llm: FakeLLM, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RAG_DENSE_THRESHOLD", "0")  # keep every candidate: only the collapse acts
    get_settings.cache_clear()
    sections = [(f"Pix > Parte {i}", f"pix na maquininha parte {i}") for i in range(8)]
    await add_document(db_pool, "https://site.getnet.com.br/pix/", "Pix", "pt", sections)
    hits = await retriever.search(_query_like("Pix", *sections[3]))
    assert [h.url for h in hits] == ["https://site.getnet.com.br/pix/"]
    assert hits[0].section == sections[3][0]


async def test_dense_covers_distinct_pages_up_to_top_5(
    db_pool: Pool, fake_llm: FakeLLM, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RAG_DENSE_THRESHOLD", "0")
    get_settings.cache_clear()
    for i in range(8):
        await add_document(
            db_pool,
            f"https://site.getnet.com.br/pix/parte-{i}/",
            f"Pix Parte {i}",
            "pt",
            [(f"Pix > Parte {i}", f"pix na maquininha parte {i}")],
        )
    hits = await retriever.search(
        _query_like("Pix Parte 2", "Pix > Parte 2", "pix na maquininha parte 2")
    )
    assert len(hits) == 5
    assert len({h.url for h in hits}) == 5
    assert hits[0].url.endswith("/parte-2/")
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)


async def test_dense_lang_filter(db_pool: Pool, fake_llm: FakeLLM) -> None:
    await seed_kb(db_pool)
    section, content = ADVANCE_EN[0]
    query = _query_like("Receivables Advance", section, content)
    assert [h.url for h in await retriever.search(query, lang="en")] == [ADVANCE_EN_URL]
    assert await retriever.search(query, lang="pt") == []
