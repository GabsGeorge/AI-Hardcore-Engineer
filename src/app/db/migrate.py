"""Plain-SQL migrations and seed (research R-12). Safe to run from the API and the ingest job
at the same time: an advisory lock serialises them."""

from datetime import date
from pathlib import Path

from app.db.pool import Pool

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
SEED_FILE = Path(__file__).parent / "seed.sql"
_LOCK_ID = 7_351_001
# Multi-statement files need the simple protocol: prepare=False overrides the pool's
# prepare_threshold=0 (required by the checkpointer).


async def migrate(pool: Pool) -> None:
    async with pool.connection() as conn:
        await conn.execute("SELECT pg_advisory_lock(%s)", (_LOCK_ID,))
        try:
            await conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                " version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
            )
            rows = await (await conn.execute("SELECT version FROM schema_migrations")).fetchall()
            applied = {r["version"] for r in rows}
            for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
                if path.stem in applied:
                    continue
                async with conn.transaction():
                    await conn.execute(path.read_text(encoding="utf-8").encode(), prepare=False)
                    await conn.execute(
                        "INSERT INTO schema_migrations (version) VALUES (%s)", (path.stem,)
                    )
        finally:
            await conn.execute("SELECT pg_advisory_unlock(%s)", (_LOCK_ID,))


async def apply_seed(pool: Pool, reference_date: date) -> bool:
    """Loads deterministic mock data. seed.sql reads the reference day from the session setting
    `app.seed_date` (e.g. `current_setting('app.seed_date')::date - 1` is "yesterday")."""
    if not SEED_FILE.exists():
        return False
    async with pool.connection() as conn, conn.transaction():
        await conn.execute(
            "SELECT set_config('app.seed_date', %s, true)", (reference_date.isoformat(),)
        )
        await conn.execute(SEED_FILE.read_text(encoding="utf-8").encode(), prepare=False)
    return True
