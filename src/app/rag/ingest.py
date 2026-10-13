"""Ingest job entry point (`python -m app.rag.ingest`): migrations, mock seed, knowledge base.

Idempotent by the sha256 of the cleaned text (REQ-RAG-02): an unchanged page is not embedded
again; a changed one has its chunks replaced, so they get new ids and the BM25 fingerprint
`(count(*), max(id))` changes (ADR 0003).
"""

import asyncio
import hashlib
from datetime import date
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.llm import get_embeddings
from app.db.migrate import apply_seed, migrate
from app.db.pool import Pool, close_pool, open_pool
from app.observability.logging import configure_logging, get_logger
from app.rag.chunking import chunk_text, passage
from app.rag.crawler import Crawler, Page, Sources, load_sources

_UPSERT_DOCUMENT = """
INSERT INTO documents (url, title, lang, source_type, content_hash, fetched_at)
VALUES (%s, %s, %s, %s, %s, now())
ON CONFLICT (url) DO UPDATE SET
    title = EXCLUDED.title, lang = EXCLUDED.lang, source_type = EXCLUDED.source_type,
    content_hash = EXCLUDED.content_hash, fetched_at = EXCLUDED.fetched_at
RETURNING id
"""
_INSERT_CHUNK = """
INSERT INTO chunks (document_id, ord, section, content, lang, embedding)
VALUES (%s, %s, %s, %s, %s, %s::vector)
"""


async def _index_page(pool: Pool, page: Page, embeddings: Any) -> int | None:
    """Chunks written for the page, or None when its content did not change."""
    digest = hashlib.sha256(page.text.encode()).hexdigest()
    async with pool.connection() as conn:
        cur = await conn.execute("SELECT content_hash FROM documents WHERE url = %s", (page.url,))
        row = await cur.fetchone()
    if row is not None and row["content_hash"] == digest:
        return None
    chunks = chunk_text(page.text, page.title)
    vectors = await embeddings.aembed_documents(
        [passage(page.title, c.section, c.content) for c in chunks]
    )
    async with pool.connection() as conn, conn.transaction():
        cur = await conn.execute(
            _UPSERT_DOCUMENT, (page.url, page.title, page.lang, page.source_type, digest)
        )
        doc = await cur.fetchone()
        if doc is None:  # RETURNING always yields the row
            raise RuntimeError("document upsert returned no row")
        await conn.execute("DELETE FROM chunks WHERE document_id = %s", (doc["id"],))
        async with conn.cursor() as batch:
            await batch.executemany(
                _INSERT_CHUNK,
                [
                    (doc["id"], i, c.section, c.content, page.lang, str([float(x) for x in v]))
                    for i, (c, v) in enumerate(zip(chunks, vectors, strict=True))
                ],
            )
    return len(chunks)


async def ingest_sources(
    pool: Pool, sources: Sources | None = None, client: httpx.AsyncClient | None = None
) -> dict[str, int]:
    """Crawl → extract → chunk → embed → upsert. Returns the ingestion report (REQ-RAG-01)."""
    sources = sources or load_sources()
    log = get_logger()
    own_client = client is None
    http = client or httpx.AsyncClient(timeout=httpx.Timeout(15.0))
    try:
        pages = await Crawler(sources, http).crawl()
    finally:
        if own_client:
            await http.aclose()

    report = {
        "sources": len(sources.seeds) + len(sources.sitemaps),
        "pages": len(pages),
        "indexed": 0,
        "unchanged": 0,
        "chunks": 0,
        "failed": 0,
    }
    embeddings = get_embeddings()
    for page in pages:
        try:
            written = await _index_page(pool, page, embeddings)
        except Exception as exc:  # one bad page (e.g. embedding API error) must not stop the run
            log.error("ingest_page_failed", url=page.url, error=type(exc).__name__)
            report["failed"] += 1
            continue
        if written is None:
            report["unchanged"] += 1
        else:
            report["indexed"] += 1
            report["chunks"] += written
            log.info("ingest_page_indexed", url=page.url, lang=page.lang, chunks=written)
    return report


async def main() -> None:
    configure_logging()
    settings = get_settings()
    pool = await open_pool(settings.database_url)
    try:
        await migrate(pool)
        seeded = await apply_seed(pool, settings.seed_reference_date or date.today())
        key = settings.openai_api_key
        if key is None or not key.get_secret_value():
            # The API waits for this job to finish: without a key it still has to succeed.
            get_logger().warning("ingest_skipped", reason="OPENAI_API_KEY is empty")
            report = dict.fromkeys(
                ("sources", "pages", "indexed", "unchanged", "chunks", "failed"), 0
            )
        else:
            report = await ingest_sources(pool)
        get_logger().info("ingest_finished", seeded=seeded, **report)
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
