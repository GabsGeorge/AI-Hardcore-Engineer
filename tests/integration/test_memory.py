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
