"""Owner reads their conversation and the final message after a human reply (REQ-API-05)."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from langchain_core.messages import AIMessage, HumanMessage

from app.api.auth import CurrentUser, current_user
from app.api.chat import graph_config
from app.api.schemas import Conversation, ConversationMessage, HandoffRef, HandoffStatus
from app.core.errors import not_found
from app.db import repo
from app.db.pool import get_pool

router = APIRouter()


@router.get("/v1/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(
    conversation_id: UUID, request: Request, user: CurrentUser = Depends(current_user)
) -> Conversation:
    handoff_row = await repo.get_conversation_handoff(get_pool(), user.id, conversation_id)
    if handoff_row is None:
        raise not_found()
    graph = request.app.state.graph
    if graph is None:
        raise not_found()
    state = await graph.aget_state(graph_config(user.id, conversation_id, request.state.trace_id))
    values: dict[str, Any] = state.values or {}
    messages: list[ConversationMessage] = []
    for m in values.get("messages") or []:
        if isinstance(m, HumanMessage):
            messages.append(ConversationMessage(role="user", content=str(m.content)))
        elif isinstance(m, AIMessage):
            messages.append(ConversationMessage(role="assistant", content=str(m.content)))
    status: HandoffStatus = handoff_row.get("handoff_status") or "none"
    return Conversation(
        conversation_id=conversation_id,
        handoff=HandoffRef(status=status, ticket_id=handoff_row.get("ticket_id")),
        last_activity_at=values.get("last_activity_at")
        or (await _last_activity(user.id, conversation_id)),
        messages=messages,
    )


async def _last_activity(user_id: str, conversation_id: UUID) -> Any:
    async with get_pool().connection() as conn:
        cur = await conn.execute(
            "SELECT last_activity_at FROM conversations WHERE id = %s AND user_id = %s",
            (conversation_id, user_id),
        )
        row = await cur.fetchone()
    if row is None:
        raise not_found()
    return row["last_activity_at"]
