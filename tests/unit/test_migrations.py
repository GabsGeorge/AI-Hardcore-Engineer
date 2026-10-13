import psycopg
import pytest
from psycopg_pool import AsyncConnectionPool

from app.db.migrate import MIGRATIONS_DIR, migrate

pytestmark = pytest.mark.req("REQ-ORC-06")


async def test_migrations_apply_once_and_are_idempotent(db_pool: AsyncConnectionPool) -> None:
    await migrate(db_pool)
    await migrate(db_pool)
    async with db_pool.connection() as conn:
        rows = await (await conn.execute("SELECT version FROM schema_migrations")).fetchall()
    assert sorted(r["version"] for r in rows) == sorted(
        p.stem for p in MIGRATIONS_DIR.glob("*.sql")
    )


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO users (id, role, display_name) VALUES ('x', 'hacker', 'X')",
        "INSERT INTO transactions (id, merchant_id, created_at, amount_cents, method, installments,"
        " status) VALUES ('t1', 'cliente1988', now(), 0, 'credit', 1, 'approved')",
        "INSERT INTO transactions (id, merchant_id, created_at, amount_cents, method, installments,"
        " status) VALUES ('t2', 'cliente1988', now(), 100, 'credit', 0, 'approved')",
        "INSERT INTO transactions (id, merchant_id, created_at, amount_cents, method, installments,"
        " status) VALUES ('t3', 'cliente1988', now(), 100, 'credit', 1, 'declined')",
        "INSERT INTO feedback (trace_id, user_id, rating) VALUES ('t', 'cliente1988', 2)",
    ],
)
async def test_checks_reject_invalid_values(db_pool: AsyncConnectionPool, sql: str) -> None:
    async with db_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO merchants (user_id, trade_name, document_masked, plan, settlement_days,"
            " anticipation_enabled) VALUES ('cliente1988', 'Loja', '**', 'Get Smart', 1, true)"
            " ON CONFLICT DO NOTHING"
        )
        with pytest.raises(psycopg.errors.CheckViolation):
            await conn.execute(sql)
