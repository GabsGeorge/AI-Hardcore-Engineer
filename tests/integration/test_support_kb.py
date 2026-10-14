"""Scenario 5: Support combines terminal status with documented steps from the KB (REQ-SUP-04)."""

from typing import Any

import httpx
import pytest
from langchain_core.messages import AIMessage

from app.db.pool import Pool
from tests.fakes import FakeLLM, make_plan
from tests.fixtures.kb import add_document, fresh_retriever  # noqa: F401

pytestmark = pytest.mark.req("REQ-SUP-04")

URL = "https://www.getnet.com.br/ajuda/sem-conexao"


@pytest.mark.usefixtures("fresh_retriever")
async def test_support_combines_data_with_knowledge_steps(
    client: httpx.AsyncClient,
    db_pool: Pool,
    fake_llm: FakeLLM,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    await add_document(
        db_pool,
        URL,
        "Terminal sem conexão",
        "pt",
        [("Passos", "Reinicie o terminal e verifique o chip 4G.")],
    )
    args: dict[str, Any] = {}
    fake_llm.script(
        supervisor=[make_plan("support", query="Minha máquina não conecta.")],
        support=[
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "diagnose_terminal", "args": args, "id": "c1", "type": "tool_call"}
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "search_knowledge_base",
                        "args": {"query": "terminal sem conexão"},
                        "id": "c2",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="Seu terminal está offline. Reinicie e verifique o chip 4G."),
        ],
    )
    resp = await client.post(
        "/v1/chat",
        json={"message": "Minha máquina não conecta."},
        headers=auth_headers["cliente1988"],
    )
    body = resp.json()
    assert resp.status_code == 200
    tool_names = [t["name"] for t in body["tools_used"]]
    assert "diagnose_terminal" in tool_names and "search_knowledge_base" in tool_names
