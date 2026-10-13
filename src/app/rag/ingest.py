"""Ingest job entry point (`python -m app.rag.ingest`): migrations, mock seed, knowledge base."""

import asyncio
from datetime import date

from app.core.config import get_settings
from app.db.migrate import apply_seed, migrate
from app.db.pool import close_pool, open_pool
from app.observability.logging import configure_logging, get_logger


async def ingest_sources() -> dict[str, int]:
    # STUB(T079): crawl, chunk, embed and upsert the public Getnet content (US1).
    return {"sources": 0, "pages": 0, "chunks": 0}


async def main() -> None:
    configure_logging()
    settings = get_settings()
    pool = await open_pool(settings.database_url)
    try:
        await migrate(pool)
        seeded = await apply_seed(pool, settings.seed_reference_date or date.today())
        report = await ingest_sources()
        get_logger().info("ingest_finished", seeded=seeded, **report)
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
