"""Support specialist through the real graph and API with the scripted LLM (scenarios 3 and 8)."""

from datetime import date
from typing import Any

import httpx
import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.agents.support import support_node
from app.db.migrate import apply_seed
from app.db.pool import Pool
from tests.fakes import FakeLLM, make_plan

pytestmark = pytest.mark.req("REQ-SUP-01")

USAGE = {"input_tokens": 80, "output_tokens": 20, "total_tokens": 100}


def _calls(*calls: tuple[str, dict[str, Any]], tokens: int = 100) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"name": name, "args": args, "id": f"call_{i}"} for i, (name, args) in enumerate(calls)
        ],
        usage_metadata=USAGE | {"total_tokens": tokens},
    )


def _answer(text: str, tokens: int = 100) -> AIMessage:
    return AIMessage(content=text, usage_metadata=USAGE | {"total_tokens": tokens})


def _input(query: str, language: str = "pt") -> Any:
    return {"subtask": {"id": "s1", "agent": "support", "query": query}, "language": language}


CONFIG: RunnableConfig = {
    "configurable": {"user_id": "cliente1988", "thread_id": "t", "trace_id": "d" * 32}
}


@pytest.fixture
async def seeded(db_pool: Pool) -> Pool:
    await apply_seed(db_pool, date(2026, 10, 13))
    return db_pool


async def test_scenario_3_settlements_of_yesterday(
    seeded: Pool,
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    question = "Quando cai o dinheiro das vendas de ontem?"
    fake_llm.script(
        supervisor=[make_plan("support", query=question)],
        support=[
            _calls(
                ("get_settlement_schedule", {"from_date": "2026-10-13", "to_date": "2026-10-13"})
            ),
            _answer("O valor de R$ 460,65 das vendas de ontem cai em 13/10/2026."),
        ],
    )
    resp = await client.post(
        "/v1/chat", json={"message": question}, headers=auth_headers["cliente1988"]
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "support" in body["route"]
    assert [(t["name"], t["status"]) for t in body["tools_used"]] == [
        ("get_settlement_schedule", "ok")
    ]
    assert body["confidence"] == 1.0
    assert body["response"] == "O valor de R$ 460,65 das vendas de ontem cai em 13/10/2026."
    # The model saw the seed values of the token's user, and never the identity itself.
    prompts = fake_llm.prompts("support")
    assert "46065" in prompts and "2026-10-13" in prompts
    assert "cliente1988" not in prompts


async def test_scenario_8_declined_transaction(
    seeded: Pool,
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    question = "Minha venda deu erro de transação recusada, o que aconteceu?"
    fake_llm.script(
        supervisor=[make_plan("support", query=question)],
        support=[
            _calls(("get_recent_transactions", {"days": 2, "status": "declined"})),
            _calls(("lookup_decline_code", {"code": "51"})),
            _answer("A venda tx-1988-004 de R$ 120,00 foi recusada (51): saldo insuficiente."),
        ],
    )
    resp = await client.post(
        "/v1/chat", json={"message": question}, headers=auth_headers["cliente1988"]
    )
    body = resp.json()
    assert "support" in body["route"]
    assert [(t["name"], t["status"]) for t in body["tools_used"]] == [
        ("get_recent_transactions", "ok"),
        ("lookup_decline_code", "ok"),
    ]
    assert body["confidence"] == 1.0
    assert "tx-1988-004" in body["response"]
    prompts = fake_llm.prompts("support")
    assert "tx-1988-004" in prompts and "12000" in prompts
    assert "Saldo" in prompts  # PT description of code 51 reached the model


async def test_node_runs_parallel_tool_calls_and_sums_tokens(
    seeded: Pool, fake_llm: FakeLLM
) -> None:
    fake_llm.script(
        support=[
            _calls(("diagnose_terminal", {}), ("get_customer_profile", {}), tokens=150),
            _answer("Your Get Mini terminal is offline (NO_SIGNAL).", tokens=50),
        ]
    )
    out = await support_node(_input("My card machine has no internet", "en"), CONFIG)
    assert out["route_trace"] == ["support"]
    assert out["tokens_used"] == 200
    [result] = out["results"]
    assert result["agent"] == "support" and result["subtask_id"] == "s1"
    assert result["error"] is None and result["confidence"] == 1.0
    assert [t["name"] for t in result["tools_used"]] == [
        "diagnose_terminal",
        "get_customer_profile",
    ]
    assert result["answer"] == "Your Get Mini terminal is offline (NO_SIGNAL)."
    prompts = fake_llm.prompts("support")
    assert "NO_SIGNAL" in prompts and "`en`" in prompts


async def test_decline_description_follows_the_subtask_language(
    seeded: Pool, fake_llm: FakeLLM
) -> None:
    fake_llm.script(support=[_calls(("lookup_decline_code", {"code": "51"})), _answer("ok")])
    await support_node(_input("What does decline code 51 mean?", "en"), CONFIG)
    assert "Insufficient" in fake_llm.prompts("support")


async def test_partial_tool_failure_halves_confidence(seeded: Pool, fake_llm: FakeLLM) -> None:
    fake_llm.script(
        support=[
            _calls(("get_customer_profile", {}), ("get_recent_transactions", {"days": 99})),
            _answer("Seu plano é Get Smart."),
        ]
    )
    [result] = (await support_node(_input("Qual meu plano?"), CONFIG))["results"]
    assert result["confidence"] == 0.5
    assert [(t["name"], t["status"]) for t in result["tools_used"]] == [
        ("get_customer_profile", "ok"),
        ("get_recent_transactions", "error"),
    ]


async def test_no_successful_tool_means_zero_confidence_and_honest_answer(
    seeded: Pool, fake_llm: FakeLLM
) -> None:
    fake_llm.script(
        support=[
            _calls(("get_recent_transactions", {"days": 0})),
            _answer("Você vendeu R$ 1.000.000,00 ontem."),
        ]
    )
    [result] = (await support_node(_input("Quanto vendi ontem?"), CONFIG))["results"]
    assert result["confidence"] == 0.0
    assert "1.000.000" not in result["answer"]
    assert "não consegui" in result["answer"].lower()


async def test_answer_without_tools_has_zero_confidence(seeded: Pool, fake_llm: FakeLLM) -> None:
    fake_llm.script(support=[_answer("Seus recebíveis estão ótimos.")])
    [result] = (await support_node(_input("Como estão meus recebíveis?"), CONFIG))["results"]
    assert result["confidence"] == 0.0 and result["tools_used"] == []
    assert "ótimos" not in result["answer"]


async def test_tool_outside_allowlist_is_denied(seeded: Pool, fake_llm: FakeLLM) -> None:
    fake_llm.script(
        support=[
            _calls(("create_ticket", {"reason": "human_request", "summary": "x"})),
            _answer("ok"),
        ]
    )
    [result] = (await support_node(_input("Abra um ticket"), CONFIG))["results"]
    assert result["tools_used"] == [{"name": "create_ticket", "status": "denied", "latency_ms": 0}]
    assert result["confidence"] == 0.0


async def test_knowledge_search_unavailable_is_reported_to_the_model(
    seeded: Pool, fake_llm: FakeLLM, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.agents.support as support

    monkeypatch.delitem(support.SUPPORT_TOOLS, "search_knowledge_base", raising=False)
    fake_llm.script(
        support=[
            _calls(("search_knowledge_base", {"query": "maquininha sem internet"})),
            _answer("ok"),
        ]
    )
    [result] = (await support_node(_input("Maquininha sem internet"), CONFIG))["results"]
    assert result["tools_used"] == []
    assert "unavailable" in fake_llm.prompts("support")


async def test_loop_stops_after_four_rounds(seeded: Pool, fake_llm: FakeLLM) -> None:
    fake_llm.script(support=[_calls(("get_customer_profile", {})) for _ in range(5)])
    out = await support_node(_input("Qual meu plano?"), CONFIG)
    [result] = out["results"]
    assert len(fake_llm.calls) == 4
    assert len(result["tools_used"]) == 4
    assert result["confidence"] == 0.0 and "não consegui" in result["answer"].lower()


async def test_model_failure_is_an_error_result(seeded: Pool, fake_llm: FakeLLM) -> None:
    fake_llm.script(support=[RuntimeError("model down")])
    [result] = (await support_node(_input("Qual meu plano?"), CONFIG))["results"]
    assert result["error"] == "model_error" and result["confidence"] == 0.0
