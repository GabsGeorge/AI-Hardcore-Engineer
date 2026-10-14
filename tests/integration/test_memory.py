"""Conversation memory: multi-turn follow-up and summarisation above the limit."""

import httpx
import pytest

from tests.fakes import FakeLLM, make_plan
from tests.fixtures.kb import fresh_retriever, rewrite  # noqa: F401

__all__ = ["fresh_retriever"]


@pytest.mark.req("REQ-MEM-03")
@pytest.mark.usefixtures("fresh_retriever")
async def test_followup_two_turns(
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    """A follow-up that refers to the previous turn ("ela") must still reach the planner
    together with the original subject, either via the running summary or via the recent
    messages the planner is given (REQ-MEM-03)."""
    fake_llm.script(
        supervisor=[make_plan("knowledge"), make_plan("knowledge")],
        knowledge_rewrite=[rewrite(), rewrite()],
    )
    first = await client.post(
        "/v1/chat",
        json={"message": "O que é a Get Smart?"},
        headers=auth_headers["cliente1988"],
    )
    assert first.status_code == 200
    second = await client.post(
        "/v1/chat",
        json={
            "message": "E quanto custa ela?",
            "conversation_id": first.json()["conversation_id"],
        },
        headers=auth_headers["cliente1988"],
    )
    assert second.status_code == 200

    supervisor_prompts = [text for role, text in fake_llm.calls if role == "supervisor"]
    assert len(supervisor_prompts) == 2
    # Each turn's planner prompt is self-contained: the second turn's prompt must still
    # carry the original subject (Get Smart) and the follow-up question.
    assert "Get Smart" in supervisor_prompts[1]
    assert "E quanto custa ela?" in supervisor_prompts[1]


@pytest.mark.req("REQ-MEM-02")
@pytest.mark.usefixtures("fresh_retriever")
async def test_summarization_over_limit(
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    # Six turns is above MEMORY_MAX_MESSAGES (8 messages: 6 human + 6 assistant → 12 total,
    # so the summariser must run on the last turn and the planner must see the summary.
    plans = [make_plan("knowledge") for _ in range(6)]
    rewrites = [rewrite() for _ in range(6)]
    fake_llm.script(
        supervisor=plans,
        knowledge_rewrite=rewrites,
        summarize=["Merchant asked about Get Smart terminals, antecipação and Pix fees."],
    )
    conversation_id = None
    questions = [
        "O que é a Get Smart?",
        "Como funciona a antecipação?",
        "Quais as taxas do Pix?",
        "A Get Smart aceita contactless?",
        "E para delivery?",
        "Qual o resumo da nossa conversa?",
    ]
    for message in questions:
        body: dict[str, object] = {"message": message}
        if conversation_id is not None:
            body["conversation_id"] = conversation_id
        resp = await client.post("/v1/chat", json=body, headers=auth_headers["cliente1988"])
        assert resp.status_code == 200
        conversation_id = resp.json()["conversation_id"]

    summarize_calls = [text for role, text in fake_llm.calls if role == "summarize"]
    assert summarize_calls, "the summariser must have been invoked above the limit"
    last_planner_prompt = next(
        text for role, text in reversed(fake_llm.calls) if role == "supervisor"
    )
    assert "Conversation summary:" in last_planner_prompt
    assert "Get Smart" in last_planner_prompt  # the running summary carries the subject
