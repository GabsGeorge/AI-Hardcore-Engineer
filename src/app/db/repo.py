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
                _scrub(target),  # targets may echo client input (e.g. a foreign user_id)
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


# --- Handoffs ---------------------------------------------------------------------------------
async def create_handoff(
    pool: Pool,
    *,
    ticket_id: UUID,
    conversation_id: UUID,
    user_id: str,
    reason: str,
    summary: str,
    context: dict[str, Any] | None,
    pending_action: dict[str, Any] | None,
    sla_minutes: int,
    expiry_hours: int,
) -> dict[str, Any]:
    """Opens a ticket and marks the conversation as awaiting the human (REQ-HITL-02)."""
    async with pool.connection() as conn, conn.transaction():
        cur = await conn.execute(
            "INSERT INTO handoffs (id, conversation_id, user_id, reason, summary, context,"
            " pending_action, sla_due_at, expires_at) VALUES (%s, %s, %s, %s, %s, %s, %s,"
            " now() + make_interval(mins => %s), now() + make_interval(hours => %s))"
            " RETURNING id, sla_due_at, expires_at",
            (
                ticket_id,
                conversation_id,
                user_id,
                reason,
                _scrub(summary),
                Jsonb(_scrub(context or {})),
                Jsonb(_scrub(pending_action)) if pending_action else None,
                sla_minutes,
                expiry_hours,
            ),
        )
        row = await cur.fetchone()
        await conn.execute(
            "UPDATE conversations SET handoff_status = 'awaiting_human' WHERE id = %s",
            (conversation_id,),
        )
        if row is None:
            raise RuntimeError("handoff insert returned no row")
        return row


async def list_handoffs(
    pool: Pool, status: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    """Operator queue, ordered by priority then creation time (REQ-HITL-06)."""
    async with pool.connection() as conn:
        if status:
            cur = await conn.execute(
                "SELECT * FROM handoffs WHERE status = %s"
                " ORDER BY (priority = 'high') DESC, created_at LIMIT %s",
                (status, limit),
            )
        else:
            cur = await conn.execute(
                "SELECT * FROM handoffs ORDER BY (priority = 'high') DESC, created_at LIMIT %s",
                (limit,),
            )
        return list(await cur.fetchall())


async def get_handoff(pool: Pool, ticket_id: UUID) -> dict[str, Any] | None:
    async with pool.connection() as conn:
        cur = await conn.execute("SELECT * FROM handoffs WHERE id = %s", (ticket_id,))
        return await cur.fetchone()


_DECISION_MAP = {"approve": "approved", "reject": "rejected"}


async def resolve_handoff(
    pool: Pool,
    *,
    ticket_id: UUID,
    operator_id: str,
    reply: str,
    action_decision: str | None,
) -> dict[str, Any]:
    """awaiting_human → resolved. Returns the row BEFORE marking resolved, so the caller can
    inspect pending_action; raises not_found when the ticket is already closed (409 upstream).

    The API accepts the imperative ``approve``/``reject``; we normalise to the stored
    past-participle (``approved``/``rejected``) so ``PendingAction`` roundtrips cleanly."""
    stored_decision = (
        _DECISION_MAP.get(action_decision, action_decision) if action_decision else None
    )
    async with pool.connection() as conn, conn.transaction():
        cur = await conn.execute(
            "UPDATE handoffs SET status = 'resolved', operator_id = %s, operator_reply = %s,"
            " pending_action = CASE WHEN pending_action IS NULL THEN NULL ELSE"
            " jsonb_set(pending_action, '{decision}',"
            " to_jsonb(COALESCE(%s::text, pending_action->>'decision'))) END,"
            " resolved_at = now()"
            " WHERE id = %s AND status = 'awaiting_human'"
            " RETURNING id, conversation_id, user_id, pending_action, operator_reply",
            (operator_id, _scrub(reply), stored_decision, ticket_id),
        )
        row = await cur.fetchone()
        if row is None:
            raise not_found()
        await conn.execute(
            "UPDATE conversations SET handoff_status = 'resolved' WHERE id = %s",
            (row["conversation_id"],),
        )
        return row


async def get_latest_handoff_for_conversation(
    pool: Pool, user_id: str, conversation_id: UUID
) -> dict[str, Any] | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT * FROM handoffs WHERE conversation_id = %s AND user_id = %s"
            " ORDER BY created_at DESC LIMIT 1",
            (conversation_id, user_id),
        )
        return await cur.fetchone()


# --- LGPD / feedback -------------------------------------------------------------------------
async def list_user_thread_ids(pool: Pool, user_id: str) -> list[str]:
    """Thread IDs do dono, no formato ``user_id:conversation_id`` usado pelo checkpointer."""
    async with pool.connection() as conn:
        cur = await conn.execute("SELECT id FROM conversations WHERE user_id = %s", (user_id,))
        rows = await cur.fetchall()
    return [f"{user_id}:{row['id']}" for row in rows]


async def delete_user_data(pool: Pool, user_id: str, *, pseudonym: str) -> dict[str, int]:
    """Apaga conversas, handoffs e feedback do dono; pseudonimiza a auditoria (REQ-SEC-09).

    O FK ``conversations → handoffs`` com ON DELETE CASCADE derruba handoffs automaticamente.
    Feedback é apagado explicitamente. ``audit_events.actor_id`` recebe o pseudônimo
    irreversível para preservar trilha de segurança sem reter a identidade.
    """
    async with pool.connection() as conn, conn.transaction():
        del_conv = await conn.execute("DELETE FROM conversations WHERE user_id = %s", (user_id,))
        del_fb = await conn.execute("DELETE FROM feedback WHERE user_id = %s", (user_id,))
        pseudo = await conn.execute(
            "UPDATE audit_events SET actor_id = %s WHERE actor_id = %s",
            (pseudonym, user_id),
        )
    return {
        "conversations": del_conv.rowcount or 0,
        "feedback": del_fb.rowcount or 0,
        "audit_events_pseudonymized": pseudo.rowcount or 0,
    }


async def insert_feedback(
    pool: Pool,
    *,
    user_id: str,
    trace_id: str,
    rating: int,
    comment: str | None,
) -> None:
    masked = _scrub(comment) if comment else None
    async with pool.connection() as conn:
        await conn.execute(
            "INSERT INTO feedback (trace_id, user_id, rating, comment) VALUES (%s, %s, %s, %s)",
            (trace_id, user_id, rating, masked),
        )
