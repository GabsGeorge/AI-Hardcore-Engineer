import re
from typing import Any

import pytest

from app.db.pool import Pool
from app.rag.crawler import Seed, SitemapSource, Sources
from app.rag.ingest import ingest_sources
from tests.fakes import FakeLLM
from tests.fixtures.site import BASE, FIXTURES, OUTSIDE, FakeSite

SOURCES = Sources(
    allowed_domains=["getnet.com.br"],
    seeds=[
        Seed(url=f"{BASE}/maquininhas/", type="page"),
        Seed(url=f"{BASE}/docs/guia-crediario.pdf", type="pdf"),
        Seed(url=OUTSIDE),
    ],
    sitemaps=[SitemapSource(url=f"{BASE}/sitemap.xml", include=["en/", "privado"])],
    max_pages=20,
)


async def _rows(pool: Pool, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    async with pool.connection() as conn:
        return await (await conn.execute(sql, params)).fetchall()


@pytest.mark.req("REQ-RAG-01", "REQ-RAG-02")
async def test_ingest_idempotent(db_pool: Pool, fake_llm: FakeLLM) -> None:
    site = FakeSite()
    async with site.client() as client:
        first = await ingest_sources(db_pool, SOURCES, client)
        chunk_ids = await _rows(db_pool, "SELECT id FROM chunks ORDER BY id")
        second = await ingest_sources(db_pool, SOURCES, client)

    assert first == {
        "sources": 4,
        "pages": 3,
        "indexed": 3,
        "unchanged": 0,
        "chunks": len(chunk_ids),
        "failed": 0,
    }
    assert first["chunks"] >= 3
    # Same content → zero reindexations, chunk ids untouched.
    assert second == {
        "sources": 4,
        "pages": 3,
        "indexed": 0,
        "unchanged": 3,
        "chunks": 0,
        "failed": 0,
    }
    assert await _rows(db_pool, "SELECT id FROM chunks ORDER BY id") == chunk_ids

    docs = {
        d["url"]: d
        for d in await _rows(
            db_pool, "SELECT url, title, lang, source_type, content_hash, fetched_at FROM documents"
        )
    }
    assert set(docs) == {
        f"{BASE}/maquininhas/",
        f"{BASE}/docs/guia-crediario.pdf",
        f"{BASE}/en/receivables-advance/",
    }
    for doc in docs.values():
        assert re.fullmatch(r"[0-9a-f]{64}", doc["content_hash"])
        assert doc["fetched_at"] is not None and doc["title"]
    assert docs[f"{BASE}/en/receivables-advance/"]["lang"] == "en"
    assert docs[f"{BASE}/maquininhas/"]["lang"] == "pt"
    assert docs[f"{BASE}/docs/guia-crediario.pdf"]["source_type"] == "pdf"

    sections = {r["section"] for r in await _rows(db_pool, "SELECT section FROM chunks")}
    assert "Maquininhas Getnet > Comparativo" in sections


@pytest.mark.req("REQ-RAG-02")
async def test_changed_document_gets_new_chunks(db_pool: Pool, fake_llm: FakeLLM) -> None:
    site = FakeSite()
    url = f"{BASE}/maquininhas/"
    async with site.client() as client:
        await ingest_sources(db_pool, SOURCES, client)
        before = await _rows(
            db_pool,
            "SELECT c.id FROM chunks c JOIN documents d ON d.id = c.document_id WHERE d.url = %s",
            (url,),
        )
        html = (FIXTURES / "maquininhas.html").read_text(encoding="utf-8")
        site.overrides[url] = html.replace("5 dias úteis", "3 dias úteis").encode()
        report = await ingest_sources(db_pool, SOURCES, client)

    assert report["indexed"] == 1 and report["unchanged"] == 2
    after = await _rows(
        db_pool,
        "SELECT c.id, c.content FROM chunks c JOIN documents d ON d.id = c.document_id "
        "WHERE d.url = %s",
        (url,),
    )
    assert after and not {r["id"] for r in after} & {r["id"] for r in before}
    assert any("3 dias úteis" in r["content"] for r in after)
    assert len(await _rows(db_pool, "SELECT id FROM documents")) == 3


@pytest.mark.req("REQ-RAG-01")
async def test_ingest_rejects_non_allowlisted_domain(db_pool: Pool, fake_llm: FakeLLM) -> None:
    site = FakeSite()
    async with site.client() as client:
        await ingest_sources(db_pool, SOURCES, client)
    urls = {r["url"] for r in await _rows(db_pool, "SELECT url FROM documents")}
    assert OUTSIDE not in urls and OUTSIDE not in site.requested
    assert f"{BASE}/privado/interno/" not in urls  # disallowed by robots.txt
    contents = " ".join(r["content"] for r in await _rows(db_pool, "SELECT content FROM chunks"))
    assert "taxa da Getnet é zero" not in contents


@pytest.mark.req("REQ-RAG-02")
async def test_embedding_failure_skips_the_page_without_partial_rows(
    db_pool: Pool, fake_llm: FakeLLM, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Broken:
        async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("embedding API down")

    monkeypatch.setattr("app.rag.ingest.get_embeddings", Broken)
    async with FakeSite().client() as client:
        report = await ingest_sources(db_pool, SOURCES, client)
    assert report["failed"] == 3 and report["indexed"] == 0 and report["chunks"] == 0
    assert await _rows(db_pool, "SELECT id FROM documents") == []
