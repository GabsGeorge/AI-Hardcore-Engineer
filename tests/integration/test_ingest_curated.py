"""A curated page goes through the same ingestion as a crawled one: chunked, embedded, stored once
and left alone when its content does not change (REQ-RAG-01, REQ-RAG-02)."""

from typing import Any

import pytest

from app.db.pool import Pool
from app.rag.crawler import CuratedSource, Sources
from app.rag.ingest import ingest_sources
from tests.fakes import FakeLLM
from tests.fixtures.site import FakeSite

URL = "https://site.getnet.com.br/todas-as-maquininhas/#offers-card"


async def _rows(pool: Pool, sql: str) -> list[dict[str, Any]]:
    async with pool.connection() as conn:
        return await (await conn.execute(sql)).fetchall()


@pytest.mark.req("REQ-RAG-01", "REQ-RAG-02")
async def test_curated_page_is_indexed_once_and_cited_by_its_section_url(
    db_pool: Pool, fake_llm: FakeLLM
) -> None:
    sources = Sources(
        allowed_domains=["getnet.com.br"],
        curated=[
            CuratedSource(
                path="todas-as-maquininhas.md",
                url=URL,
                title="Maquininhas Getnet: taxas por faixa de faturamento, preços e recursos",
            )
        ],
    )
    async with FakeSite().client() as client:
        first = await ingest_sources(db_pool, sources, client)
        second = await ingest_sources(db_pool, sources, client)

    assert first["sources"] == 1 and first["pages"] == 1 and first["failed"] == 0
    assert first["indexed"] == 1 and first["chunks"] > 5
    assert second["indexed"] == 0 and second["unchanged"] == 1 and second["chunks"] == 0

    [doc] = await _rows(db_pool, "SELECT url, lang, source_type FROM documents")
    assert doc["url"] == URL and doc["lang"] == "pt" and doc["source_type"] == "page"
    stored = await _rows(db_pool, "SELECT section, content FROM chunks")
    joined = " ".join(f"{c['section']} {c['content']}" for c in stored)
    assert "0,85%" in joined and "Simulador de vendas" in joined
