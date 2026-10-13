"""POST /v1/chat bodies against ChatResponse (pydantic) and contracts/openapi.yaml, in scripted
Knowledge scenarios run through the real graph."""

from pathlib import Path
from typing import Any

import httpx
import jsonschema_rs
import pytest
import yaml

from app.api.schemas import ChatResponse
from app.db.pool import Pool
from app.tools import knowledge_tools
from tests.fakes import FakeLLM, make_plan
from tests.fixtures.kb import SMART_URL, answer, fresh_retriever, rewrite, seed_kb

__all__ = ["fresh_retriever"]
pytestmark = [
    pytest.mark.req("REQ-API-01", "REQ-API-02"),
    pytest.mark.usefixtures("fresh_retriever"),
]

OPENAPI = Path(__file__).parents[2] / "specs/001-multi-agent-support/contracts/openapi.yaml"


def _validate(body: dict[str, Any]) -> ChatResponse:
    components = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))["components"]
    schema = {"$ref": "#/components/schemas/ChatResponse", "components": components}
    jsonschema_rs.Draft202012Validator(schema).validate(body)
    return ChatResponse.model_validate(body)


async def _chat(client: httpx.AsyncClient, headers: dict[str, str], message: str) -> ChatResponse:
    resp = await client.post("/v1/chat", json={"message": message}, headers=headers)
    assert resp.status_code == 200, resp.text
    return _validate(resp.json())


async def test_knowledge_answer_with_kb_sources(
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    db_pool: Pool,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    await seed_kb(db_pool)
    question = "Qual a diferença entre a Get Smart e a Get Clássica?"
    fake_llm.script(
        supervisor=[make_plan("knowledge", query=question)],
        knowledge_rewrite=[rewrite(("get smart tela touch", "pt"))],
        knowledge=[answer("A Get Smart tem tela touch e Wi-Fi [1].", 0.9)],
    )
    body = await _chat(client, auth_headers["cliente1988"], question)
    assert body.route == [
        "input_guardrail",
        "supervisor",
        "knowledge",
        "supervisor",
        "synthesize",
        "output_guardrail",
    ]
    assert body.response == "A Get Smart tem tela touch e Wi-Fi [1]."
    assert [(s.url, s.kind) for s in body.sources] == [(SMART_URL, "kb")]
    assert [t.name for t in body.tools_used] == ["search_knowledge_base"] * 2
    assert body.confidence == pytest.approx(0.75)


async def test_general_question_with_web_source(
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    db_pool: Pool,
    auth_headers: dict[str, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def ddgs(query: str, max_results: int) -> list[dict[str, str]]:
        return [
            {"title": "Euro hoje", "href": "https://economia.example.com/euro", "body": "R$ 6,10"}
        ]

    monkeypatch.setattr(knowledge_tools, "ddgs_text", ddgs)
    question = "Qual a cotação do euro hoje? (contrato)"
    fake_llm.script(
        supervisor=[make_plan("knowledge", query=question)],
        knowledge_rewrite=[rewrite(general=True)],
        knowledge=[answer("O euro está a R$ 6,10, segundo Euro hoje [1].", 0.8)],
    )
    body = await _chat(client, auth_headers["cliente1988"], question)
    [source] = body.sources
    assert source.kind == "web" and source.retrieved_at is not None
    assert "knowledge" in body.route and body.route[-2:] == ["synthesize", "output_guardrail"]


async def test_unknown_product_never_invents(
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    db_pool: Pool,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    await seed_kb(db_pool)
    question = "Quais as funções da Get Ultra Max 9000?"
    fake_llm.script(
        supervisor=[make_plan("knowledge", query=question)], knowledge_rewrite=[rewrite()]
    )
    body = await _chat(client, auth_headers["cliente1988"], question)
    assert "knowledge" in body.route
    assert body.sources == []
    assert "Wi-Fi" not in body.response and "touch" not in body.response
