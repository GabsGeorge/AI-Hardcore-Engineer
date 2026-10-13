"""Parameterised SQL for users, conversations and audit. Every read of user-owned data filters
by the owner."""

from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from app.core.errors import not_found
from app.db.pool import Pool
from app.guardrails.pii import mask


async def get_user(pool: Pool, user_id: str) -> dict[str, Any] | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT id, role, display_name FROM users WHERE id = %s", (user_id,)
        )
        return await cur.fetchone()


def _scrub(value: Any) -> Any:
    if isinstance(value, str):
        return mask(value)[0]
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


async def insert_audit_event(
    pool: Pool,
    *,
    actor_id: str,
    actor_role: str,
    action: str,
    target: str,
    outcome: str,
    trace_id: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            "INSERT INTO audit_events (actor_id, actor_role, action, target, outcome, trace_id,"
            " metadata) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                actor_id,
                actor_role,
                action,
                target,
                outcome,
                trace_id,
                Jsonb(_scrub(metadata or {})),
            ),
        )


async def get_or_create_conversation(
    pool: Pool, user_id: str, conversation_id: UUID | None
) -> UUID:
    """Returns the caller's conversation. Someone else's or a missing id is the same 404, so the
    API never reveals that a conversation exists."""
    async with pool.connection() as conn:
        if conversation_id is None:
            new_id = uuid4()
            await conn.execute(
                "INSERT INTO conversations (id, user_id) VALUES (%s, %s)", (new_id, user_id)
            )
            return new_id
        cur = await conn.execute(
            "UPDATE conversations SET last_activity_at = now() WHERE id = %s AND user_id = %s"
            " RETURNING id",
            (conversation_id, user_id),
        )
        if await cur.fetchone() is None:
            raise not_found()
        return conversation_id


async def get_conversation_handoff(
    pool: Pool, user_id: str, conversation_id: UUID
) -> dict[str, Any] | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT c.handoff_status, h.id AS ticket_id FROM conversations c"
            " LEFT JOIN LATERAL (SELECT id FROM handoffs WHERE conversation_id = c.id"
            "   ORDER BY created_at DESC LIMIT 1) h ON true"
            " WHERE c.id = %s AND c.user_id = %s",
            (conversation_id, user_id),
        )
        return await cur.fetchone()
