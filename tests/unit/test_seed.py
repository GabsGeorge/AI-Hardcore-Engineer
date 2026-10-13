from datetime import date
from typing import Any

import pytest

from app.db.migrate import apply_seed
from app.db.pool import Pool

REFERENCE = date(2026, 10, 13)
YESTERDAY = date(2026, 10, 12)
TZ = "America/Sao_Paulo"

pytestmark = pytest.mark.req("REQ-SUP-02")


async def _rows(pool: Pool, sql: str, *params: Any) -> list[dict[str, Any]]:
    async with pool.connection() as conn:
        return await (await conn.execute(sql, params)).fetchall()


async def _snapshot(pool: Pool) -> dict[str, list[dict[str, Any]]]:
    tables = ["users", "merchants", "terminals", "decline_codes", "transactions", "settlements"]
    out = {}
    for table in tables:
        key = "code" if table == "decline_codes" else "user_id" if table == "merchants" else "id"
        cols = "*" if table != "users" else "id, role, display_name"
        out[table] = await _rows(pool, f"SELECT {cols} FROM {table} ORDER BY {key}")  # noqa: S608
    return out


async def test_seed_has_users_and_merchants(db_pool: Pool) -> None:
    assert await apply_seed(db_pool, REFERENCE) is True
    users = {r["id"]: r["role"] for r in await _rows(db_pool, "SELECT id, role FROM users")}
    assert users == {
        "cliente1988": "merchant",
        "cliente2024": "merchant",
        "cliente3033": "merchant",
        "operador01": "operator",
        "admin01": "admin",
    }
    merchants = await _rows(db_pool, "SELECT user_id FROM merchants ORDER BY user_id")
    assert [m["user_id"] for m in merchants] == ["cliente1988", "cliente2024", "cliente3033"]


async def test_cliente1988_has_yesterdays_sales_with_settlements(db_pool: Pool) -> None:
    await apply_seed(db_pool, REFERENCE)
    rows = await _rows(
        db_pool,
        "SELECT t.id, s.expected_date, s.status FROM transactions t"
        " JOIN settlements s ON s.transaction_id = t.id"
        " WHERE t.merchant_id = 'cliente1988' AND t.status = 'approved'"
        " AND (t.created_at AT TIME ZONE %s)::date = %s",
        TZ,
        YESTERDAY,
    )
    assert len(rows) == 3
    assert {(r["expected_date"], r["status"]) for r in rows} == {(REFERENCE, "scheduled")}


async def test_cliente1988_has_an_offline_terminal_with_error(db_pool: Pool) -> None:
    await apply_seed(db_pool, REFERENCE)
    rows = await _rows(
        db_pool,
        "SELECT id, last_error FROM terminals WHERE merchant_id = 'cliente1988'"
        " AND status = 'offline'",
    )
    assert len(rows) == 1 and rows[0]["last_error"]


async def test_cliente1988_has_a_recent_declined_transaction_with_known_code(
    db_pool: Pool,
) -> None:
    await apply_seed(db_pool, REFERENCE)
    rows = await _rows(
        db_pool,
        "SELECT t.id, d.code, d.description_pt, d.description_en, d.action_pt, d.action_en"
        " FROM transactions t JOIN decline_codes d ON d.code = t.decline_code"
        " WHERE t.merchant_id = 'cliente1988' AND t.status = 'declined'"
        " AND (t.created_at AT TIME ZONE %s)::date >= %s",
        TZ,
        YESTERDAY,
    )
    assert len(rows) == 1
    assert all(rows[0][k] for k in ("description_pt", "description_en", "action_pt", "action_en"))
    codes = await _rows(db_pool, "SELECT code FROM decline_codes ORDER BY code")
    assert {"05", "51", "57"} <= {c["code"] for c in codes}


async def test_seed_is_relative_to_the_reference_date(db_pool: Pool) -> None:
    await apply_seed(db_pool, date(2027, 1, 2))
    rows = await _rows(
        db_pool,
        "SELECT DISTINCT s.expected_date FROM settlements s JOIN transactions t"
        " ON t.id = s.transaction_id WHERE s.merchant_id = 'cliente1988'"
        " AND (t.created_at AT TIME ZONE %s)::date = %s",
        TZ,
        date(2027, 1, 1),
    )
    assert [r["expected_date"] for r in rows] == [date(2027, 1, 2)]


async def test_seed_is_idempotent(db_pool: Pool) -> None:
    await apply_seed(db_pool, REFERENCE)
    first = await _snapshot(db_pool)
    await apply_seed(db_pool, REFERENCE)
    assert await _snapshot(db_pool) == first
    assert all(first[t] for t in first)
