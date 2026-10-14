"""Conversation memory node: folds old messages into `summary` so the planner's context stays
bounded (REQ-MEM-02). Runs before the supervisor; a summarisation error never corrupts the
conversation (we return no update)."""

from typing import Any

from langchain_core.messages import HumanMessage, RemoveMessage, SystemMessage

from app.core.llm import get_model
from app.core.prompts import load_prompt
from app.graph.state import AgentState

MEMORY_MAX_MESSAGES = 8  # when the thread grows beyond this, fold the oldest into `summary`
KEEP_RECENT = 4  # the planner also looks at the last few messages (supervisor.RECENT_MESSAGES)


async def summarize(state: AgentState) -> dict[str, Any]:
    messages = list(state.get("messages") or [])
    if len(messages) <= MEMORY_MAX_MESSAGES:
        return {}
    old, _keep = messages[:-KEEP_RECENT], messages[-KEEP_RECENT:]
    if not old:
        return {}
    previous = state.get("summary") or ""
    transcript = "\n".join(
        f"{type(m).__name__}: {str(m.content)[:400]}" for m in old if getattr(m, "content", "")
    )
    prompt = load_prompt("summarize")
    try:
        reply = await get_model("summarize").ainvoke(
            [
                SystemMessage(content=prompt),
                HumanMessage(
                    content=(
                        f"Previous summary (may be empty):\n{previous}\n\n"
                        f"Older messages to fold in:\n{transcript}"
                    )
                ),
            ]
        )
    except Exception:
        # A summarisation failure must never corrupt the conversation.
        return {}
    summary = str(getattr(reply, "content", "")).strip()
    if not summary:
        return {}
    # Drop the old messages: the planner now relies on `summary` + the recent ones.
    return {
        "summary": summary,
        "messages": [RemoveMessage(id=m.id) for m in old if getattr(m, "id", None)],
    }
