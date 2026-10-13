from typing import Any

import httpx
import pytest
from langchain_core.messages import HumanMessage

from app.graph.synthesize import degraded_response, guess_language, safe_response, synthesize
from tests.fakes import FakeLLM

pytestmark = pytest.mark.req("REQ-ORC-07")

PT = "Qual a diferença entre a Get Clássica e a Get Smart?"
EN = "What is the difference between Get Clássica and Get Smart?"


def _state(message: str, language: str | None, results: list[Any] | None = None) -> Any:
    return {
        "messages": [HumanMessage(content=message)],
        "language": language,
        "results": results or [],
    }


def _answer(agent: str, text: str) -> dict[str, Any]:
    return {
        "subtask_id": agent,
        "agent": agent,
        "answer": text,
        "confidence": 0.9,
        "sources": [],
        "tools_used": [],
        "error": None,
    }


@pytest.mark.parametrize(
    ("message", "language", "degraded", "safe"),
    [(PT, "pt", "Não consegui", "Não posso"), (EN, "en", "I couldn't", "I can't")],
)
async def test_terminal_replies_follow_the_planner_language(
    message: str, language: str, degraded: str, safe: str
) -> None:
    assert (await degraded_response(_state(message, language)))["final_response"].startswith(
        degraded
    )
    assert (await safe_response(_state(message, language)))["final_response"].startswith(safe)


async def test_synthesis_asks_the_model_for_the_user_language(fake_llm: FakeLLM) -> None:
    fake_llm.script(synthesize=["Here is the answer."])
    out = await synthesize(_state(EN, "en", [_answer("knowledge", "a"), _answer("support", "b")]))
    assert out["final_response"] == "Here is the answer."
    assert "`en`" in fake_llm.prompts("synthesize")


def test_language_guess_before_planning() -> None:
    assert guess_language(PT) == "pt"
    assert guess_language(EN) == "en"
    assert guess_language("Can I sell through WhatsApp using the Payment Link?") == "en"
    assert guess_language("Preciso de conta bancária para receber via Pix?") == "pt"


async def test_api_degraded_answer_before_planning_uses_guessed_language(
    client: httpx.AsyncClient, fake_llm: FakeLLM, auth_headers: dict[str, dict[str, str]]
) -> None:
    fake_llm.script(supervisor=[ValueError("planner unavailable")])
    resp = await client.post(
        "/v1/chat",
        json={"message": "Can I sell through WhatsApp using the Payment Link?"},
        headers=auth_headers["cliente1988"],
    )
    assert resp.status_code == 200
    assert resp.json()["response"].startswith("I couldn't")
