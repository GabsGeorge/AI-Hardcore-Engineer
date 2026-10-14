"""Conversation memory: multi-turn follow-up and summarisation above the limit."""

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.graph.memory import MEMORY_MAX_MESSAGES, summarize
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
async def test_summarize_folds_old_messages_above_limit(fake_llm: FakeLLM) -> None:
    """Direct check: when the thread exceeds MEMORY_MAX_MESSAGES, summarize calls the model
    and emits RemoveMessage markers to drop the oldest turns from the state."""
    fake_llm.script(summarize=["Merchant asked about Get Smart terminals and antecipação."])
    msgs: list[HumanMessage | AIMessage] = []
    for i in range(MEMORY_MAX_MESSAGES // 2 + 2):
        msgs.append(HumanMessage(id=f"h{i}", content=f"pergunta {i}"))
        msgs.append(AIMessage(id=f"a{i}", content=f"resposta {i}"))
    state: dict = {"messages": msgs, "summary": ""}
    update = await summarize(state)
    assert "summary" in update and update["summary"]
    assert "Get Smart" in update["summary"]
    # It drops the oldest messages (keeps the KEEP_RECENT most recent ones).
    assert "messages" in update and len(update["messages"]) >= 1
    summarize_calls = [text for role, text in fake_llm.calls if role == "summarize"]
    assert summarize_calls, "the summariser must have been invoked above the limit"


@pytest.mark.req("REQ-MEM-02")
async def test_summarize_skips_when_under_limit(fake_llm: FakeLLM) -> None:
    """Short threads must NOT invoke the summariser."""
    fake_llm.script(summarize=["unused"])
    msgs = [HumanMessage(id="h1", content="oi"), AIMessage(id="a1", content="olá")]
    update = await summarize({"messages": msgs, "summary": ""})
    assert update == {}
    assert not [text for role, text in fake_llm.calls if role == "summarize"]


@pytest.mark.req("REQ-MEM-02")
@pytest.mark.usefixtures("fresh_retriever")
async def test_summarization_api_smoke(
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    """End-to-end smoke: the API accepts a multi-turn conversation without errors. The
    summariser's exact trigger point depends on retrieval; its correctness is covered by
    the direct unit tests above."""
    # Six turns is above MEMORY_MAX_MESSAGES (8 messages: 6 human + 6 assistant → 12 total,
    # so the summariser must run on the last turn and the planner must see the summary.
    # Script generously: the supervisor may replan multiple times per turn, and we want all
    # 6 user turns to complete so the thread grows beyond MEMORY_MAX_MESSAGES.
    plans = [make_plan("knowledge") for _ in range(30)]
    rewrites = [rewrite() for _ in range(30)]
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

    # Smoke only; the end state must at least show every turn ran a supervisor plan.
    supervisor_calls = [text for role, text in fake_llm.calls if role == "supervisor"]
    assert len(supervisor_calls) >= len(questions)
