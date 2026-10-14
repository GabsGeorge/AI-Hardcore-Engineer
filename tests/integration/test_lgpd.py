"""Exclusão de dados do dono (REQ-SEC-09): remove conversas, feedback, pseudonimiza auditoria."""

from __future__ import annotations

import httpx
import pytest

from app.db.pool import Pool
from tests.fakes import FakeLLM, make_plan
from tests.fixtures.kb import fresh_retriever, rewrite  # noqa: F401


@pytest.mark.req("REQ-SEC-09")
@pytest.mark.usefixtures("fresh_retriever")
async def test_delete_my_data_removes_conversations_and_pseudonymizes_audit(
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    db_pool: Pool,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    fake_llm.script(supervisor=[make_plan("knowledge")], knowledge_rewrite=[rewrite()])
    headers = auth_headers["cliente1988"]

    # Um turno gera a conversa; uma tentativa com user_id divergente gera um evento de auditoria.
    chat_resp = await client.post("/v1/chat", json={"message": "oi"}, headers=headers)
    assert chat_resp.status_code == 200
    audit_resp = await client.post(
        "/v1/chat", json={"message": "x", "user_id": "cliente2024"}, headers=headers
    )
    assert audit_resp.status_code == 403

    delete = await client.delete("/v1/me/data", headers=headers)
    assert delete.status_code == 200
    body = delete.json()
    assert body["deleted"]["conversations"] >= 1
    assert body["pseudonym"].startswith("deleted:")

    # Conversas do dono sumiram
    async with db_pool.connection() as conn:
        cur = await conn.execute(
            "SELECT count(*)::int AS n FROM conversations WHERE user_id = %s", ("cliente1988",)
        )
        row = await cur.fetchone()
        assert row and row["n"] == 0

        # Auditoria não some: foi pseudonimizada
        cur = await conn.execute(
            "SELECT count(*)::int AS n FROM audit_events WHERE actor_id = %s", ("cliente1988",)
        )
        row = await cur.fetchone()
        assert row and row["n"] == 0
        cur = await conn.execute(
            "SELECT count(*)::int AS n FROM audit_events WHERE actor_id = %s", (body["pseudonym"],)
        )
        row = await cur.fetchone()
        assert row and row["n"] >= 1
