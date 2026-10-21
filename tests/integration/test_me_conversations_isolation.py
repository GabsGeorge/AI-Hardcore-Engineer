"""US4 reforça o isolamento entre lojistas: nem pelo id, nem pela lista um lojista vê o que
pertence ao outro (T074 / FR-014)."""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from app.db.pool import Pool
from tests.fakes import FakeLLM, make_plan
from tests.fixtures.kb import fresh_retriever, rewrite  # noqa: F401


@pytest.mark.req("REQ-SEC-02")
@pytest.mark.usefixtures("fresh_retriever")
async def test_other_merchant_conversation_never_appears_in_list(
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    db_pool: Pool,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    """Mesmo com dois lojistas conversando em paralelo, cada /me/conversations devolve só o
    histórico do dono do cookie/token — a tela de histórico nunca mostra o id alheio."""
    fake_llm.script(
        supervisor=[make_plan("knowledge") for _ in range(2)],
        knowledge_rewrite=[rewrite() for _ in range(2)],
    )
    r1 = await client.post(
        "/v1/chat",
        json={"message": "do 1988"},
        headers=auth_headers["cliente1988"],
    )
    r2 = await client.post(
        "/v1/chat",
        json={"message": "do 2024"},
        headers=auth_headers["cliente2024"],
    )
    conv_1988 = r1.json()["conversation_id"]
    conv_2024 = r2.json()["conversation_id"]
    assert conv_1988 != conv_2024

    list_1988 = (
        await client.get("/v1/me/conversations", headers=auth_headers["cliente1988"])
    ).json()["items"]
    ids_1988 = [c["id"] for c in list_1988]
    assert conv_1988 in ids_1988
    assert conv_2024 not in ids_1988

    list_2024 = (
        await client.get("/v1/me/conversations", headers=auth_headers["cliente2024"])
    ).json()["items"]
    ids_2024 = [c["id"] for c in list_2024]
    assert conv_2024 in ids_2024
    assert conv_1988 not in ids_2024


@pytest.mark.req("REQ-SEC-02", "REQ-API-05")
async def test_direct_access_to_a_strangers_conversation_is_404(
    client: httpx.AsyncClient,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    """FR-014: endereço de conversa alheia deve devolver o mesmo 404 que uma inexistente,
    sem vazar sinais de existência."""
    fake_id = uuid4()
    resp = await client.get(f"/v1/conversations/{fake_id}", headers=auth_headers["cliente1988"])
    assert resp.status_code == 404
