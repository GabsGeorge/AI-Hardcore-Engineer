"""Parameterised SQL for the Support tools (REQ-SUP-01). Every query of merchant data filters by
`merchant_id`, which callers take from the server-side identity only (REQ-SEC-03): another
merchant's terminal or transaction is simply not found, never an error that reveals it exists."""

from datetime import date
from typing import Any

from app.db.pool import Pool


async def _fetch(pool: Pool, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    async with pool.connection() as conn:
        return await (await conn.execute(sql, params)).fetchall()


async def settlement_schedule(
    pool: Pool, merchant_id: str, from_date: date, to_date: date
) -> list[dict[str, Any]]:
    return await _fetch(
        pool,
        "SELECT expected_date, sum(amount_cents)::bigint AS amount_cents, status,"
        " count(*)::int AS transaction_count FROM settlements"
        " WHERE merchant_id = %s AND expected_date BETWEEN %s AND %s"
        " GROUP BY expected_date, status ORDER BY expected_date, status",
        (merchant_id, from_date, to_date),
    )


async def terminals(
    pool: Pool, merchant_id: str, terminal_id: str | None = None
) -> list[dict[str, Any]]:
    return await _fetch(
        pool,
        "SELECT id, model, connectivity, status, last_seen_at, last_error FROM terminals"
        " WHERE merchant_id = %s AND (%s::text IS NULL OR id = %s) ORDER BY id",
        (merchant_id, terminal_id, terminal_id),
    )


async def recent_transactions(
    pool: Pool, merchant_id: str, since: date, status: str | None, limit: int
) -> list[dict[str, Any]]:
    """Sales from the start of `since` (merchant local time) on, newest first."""
    return await _fetch(
        pool,
        "SELECT id, created_at, amount_cents, method, installments, status, decline_code"
        " FROM transactions WHERE merchant_id = %s"
        " AND created_at >= %s::date::timestamp AT TIME ZONE 'America/Sao_Paulo'"
        " AND (%s::text IS NULL OR status = %s) ORDER BY created_at DESC, id LIMIT %s",
        (merchant_id, since, status, status, limit),
    )


async def decline_code(pool: Pool, code: str) -> dict[str, Any] | None:
    """Public reference table: the same for every merchant."""
    rows = await _fetch(pool, "SELECT * FROM decline_codes WHERE code = %s", (code,))
    return rows[0] if rows else None


async def customer_profile(pool: Pool, merchant_id: str) -> dict[str, Any] | None:
    rows = await _fetch(
        pool,
        "SELECT m.trade_name, m.plan, m.settlement_days, m.anticipation_enabled,"
        " (SELECT count(*) FROM terminals t WHERE t.merchant_id = m.user_id)::int"
        " AS terminal_count FROM merchants m WHERE m.user_id = %s",
        (merchant_id,),
    )
    return rows[0] if rows else None
