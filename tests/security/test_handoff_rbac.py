"""Lojista não pode abrir a fila do operador — 403 forbidden_role (T068 / FR-024, REQ-SEC-06)."""

from __future__ import annotations

import httpx
import pytest


@pytest.mark.req("REQ-SEC-06")
async def test_merchant_cannot_list_the_queue(
    client: httpx.AsyncClient, auth_headers: dict[str, dict[str, str]]
) -> None:
    resp = await client.get(
        "/v1/handoffs?status=awaiting_human", headers=auth_headers["cliente1988"]
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden_role"


@pytest.mark.req("REQ-SEC-06")
async def test_merchant_cannot_reply_to_a_ticket(
    client: httpx.AsyncClient, auth_headers: dict[str, dict[str, str]]
) -> None:
    """Even a well-formed ticket id gets rejected at the role check, before the handler runs."""
    resp = await client.post(
        "/v1/handoffs/00000000-0000-0000-0000-000000000001/reply",
        json={"reply": "oi"},
        headers=auth_headers["cliente1988"],
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden_role"
