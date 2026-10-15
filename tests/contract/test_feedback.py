"""Contrato de ``POST /v1/feedback`` (REQ-OBS-05)."""

from __future__ import annotations

import httpx
import pytest

from app.db.pool import Pool

_TRACE = "0123456789abcdef0123456789abcdef"


@pytest.mark.req("REQ-OBS-05")
async def test_feedback_links_to_trace_and_persists(
    client: httpx.AsyncClient,
    db_pool: Pool,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    resp = await client.post(
        "/v1/feedback",
        json={"trace_id": _TRACE, "rating": 1, "comment": "muito bom"},
        headers=auth_headers["cliente1988"],
    )
    assert resp.status_code == 202
    async with db_pool.connection() as conn:
        row = await (
            await conn.execute(
                "SELECT user_id, rating, comment, trace_id FROM feedback WHERE trace_id = %s",
                (_TRACE,),
            )
        ).fetchone()
    assert row is not None
    assert row["user_id"] == "cliente1988"
    assert row["rating"] == 1
    assert row["trace_id"] == _TRACE


@pytest.mark.req("REQ-OBS-05")
async def test_feedback_masks_pii_in_comment(
    client: httpx.AsyncClient,
    db_pool: Pool,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    resp = await client.post(
        "/v1/feedback",
        json={"trace_id": _TRACE, "rating": -1, "comment": "fala no fulano.silva@example.com"},
        headers=auth_headers["cliente1988"],
    )
    assert resp.status_code == 202
    async with db_pool.connection() as conn:
        row = await (
            await conn.execute("SELECT comment FROM feedback WHERE trace_id = %s", (_TRACE,))
        ).fetchone()
    assert row is not None
    assert "fulano.silva@example.com" not in row["comment"], "PII bruta não pode persistir"


@pytest.mark.req("REQ-OBS-05")
async def test_feedback_comment_limit_enforced(
    client: httpx.AsyncClient, auth_headers: dict[str, dict[str, str]]
) -> None:
    resp = await client.post(
        "/v1/feedback",
        json={"trace_id": _TRACE, "rating": 1, "comment": "x" * 1001},
        headers=auth_headers["cliente1988"],
    )
    assert resp.status_code == 422


@pytest.mark.req("REQ-OBS-05")
async def test_feedback_rating_must_be_plus_or_minus_one(
    client: httpx.AsyncClient, auth_headers: dict[str, dict[str, str]]
) -> None:
    resp = await client.post(
        "/v1/feedback",
        json={"trace_id": _TRACE, "rating": 0},
        headers=auth_headers["cliente1988"],
    )
    assert resp.status_code == 422
