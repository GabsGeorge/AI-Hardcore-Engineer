"""Compound question fans out to Knowledge and Support in one run (REQ-ORC-02)."""

from typing import Any

import httpx
import pytest
from langchain_core.messages import AIMessage

from tests.fakes import FakeLLM, make_plan
from tests.fixtures.kb import fresh_retriever, rewrite  # noqa: F401

pytestmark = pytest.mark.req("REQ-ORC-02")


@pytest.mark.usefixtures("fresh_retriever")
async def test_compound_question_fans_out(
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    """Scenarios 5 + 6: 'minha máquina não conecta e como funciona a antecipação' should route
    both to Knowledge and Support in the same run and come back as one synthesized reply."""
    args: dict[str, Any] = {}
    fake_llm.script(
        supervisor=[make_plan("knowledge", "support", language="pt")],
        knowledge_rewrite=[rewrite()],
        knowledge=[{"answer": "A antecipação adianta recebíveis.", "confidence": 0.9, "cited": []}],
        support=[
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "diagnose_terminal", "args": args, "id": "c1", "type": "tool_call"}
                ],
            ),
            AIMessage(content="Seu terminal está online."),
        ],
        synthesize=["Antecipação e terminal: respondido."],
    )
    resp = await client.post(
        "/v1/chat",
        json={"message": "Minha máquina não conecta e como funciona a antecipação?"},
        headers=auth_headers["cliente1988"],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "knowledge" in body["route"] and "support" in body["route"]
    assert body["route"].count("synthesize") == 1
    assert body["response"] == "Antecipação e terminal: respondido."
