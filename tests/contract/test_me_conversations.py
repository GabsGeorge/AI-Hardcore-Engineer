"""GET /v1/me/conversations lists the merchant's own, newest first (T051 / FR-014)."""

from __future__ import annotations

import httpx
import pytest

from app.db.pool import Pool
from tests.fakes import FakeLLM, make_plan
from tests.fixtures.kb import fresh_retriever, rewrite  # noqa: F401


@pytest.mark.req("REQ-API-02")
@pytest.mark.usefixtures("fresh_retriever")
async def test_lists_only_the_merchants_own_conversations(
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    db_pool: Pool,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    fake_llm.script(
        supervisor=[make_plan("knowledge") for _ in range(3)],
        knowledge_rewrite=[rewrite() for _ in range(3)],
    )
    await client.post(
        "/v1/chat",
        json={"message": "pergunta do 1988"},
        headers=auth_headers["cliente1988"],
    )
    await client.post(
        "/v1/chat",
        json={"message": "outra do 1988"},
        headers=auth_headers["cliente1988"],
    )
    await client.post(
        "/v1/chat",
        json={"message": "pergunta do 2024"},
        headers=auth_headers["cliente2024"],
    )

    resp = await client.get("/v1/me/conversations", headers=auth_headers["cliente1988"])
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["items"], list)
    assert len(body["items"]) == 2  # só as do 1988
    # Mais recente primeiro: as duas aqui têm last_activity_at em ordem decrescente
    activities = [item["last_activity_at"] for item in body["items"]]
    assert activities == sorted(activities, reverse=True)


@pytest.mark.req("REQ-API-02")
async def test_pagination_by_cursor(
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    db_pool: Pool,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    """limit=1 + cursor devolve a próxima mais antiga; sem cursor começa pela mais nova."""
    fake_llm.script(
        supervisor=[make_plan("knowledge") for _ in range(3)],
        knowledge_rewrite=[rewrite() for _ in range(3)],
    )
    for i in range(3):
        await client.post(
            "/v1/chat",
            json={"message": f"turn {i}"},
            headers=auth_headers["cliente1988"],
        )

    first = (
        await client.get(
            "/v1/me/conversations", params={"limit": 1}, headers=auth_headers["cliente1988"]
        )
    ).json()
    assert len(first["items"]) == 1
    assert first["next_cursor"]
    second = (
        await client.get(
            "/v1/me/conversations",
            params={"limit": 1, "cursor": first["next_cursor"]},
            headers=auth_headers["cliente1988"],
        )
    ).json()
    assert len(second["items"]) == 1
    assert second["items"][0]["id"] != first["items"][0]["id"]


@pytest.mark.req("REQ-API-02", "REQ-SEC-06")
async def test_operator_sees_an_empty_list(
    client: httpx.AsyncClient, auth_headers: dict[str, dict[str, str]]
) -> None:
    """Operador não é dono de conversas; não deve ver nada aqui, nem com dados do seed."""
    resp = await client.get("/v1/me/conversations", headers=auth_headers["operador01"])
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "next_cursor": None}
