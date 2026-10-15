"""SLA, ticket expiry and retention purge, every 60 s under one advisory lock (REQ-HITL-05,
REQ-SEC-09). ``run_tick`` is exposed so tests drive a tick without waiting for the clock."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from langgraph.types import Command

from app.core.config import get_settings
from app.db.pool import Pool
from app.observability.logging import get_logger

_LOCK_ID = 7_300_914_257
# LangGraph keeps conversation text here, keyed by thread_id, with no FK to conversations.
_CHECKPOINT_TABLES = ("checkpoint_writes", "checkpoint_blobs", "checkpoints")


async def _sla_sweep(conn: Any) -> int:
    cur = await conn.execute(
        "UPDATE handoffs SET priority = 'high'"
        " WHERE status = 'awaiting_human' AND priority = 'normal' AND sla_due_at < now()"
    )
    return cur.rowcount or 0


async def _expire_sweep(conn: Any, graph: Any) -> int:
    rows = await (
        await conn.execute(
            "SELECT id, user_id, conversation_id FROM handoffs"
            " WHERE status = 'awaiting_human' AND expires_at < now()"
        )
    ).fetchall()
    for row in rows:
        if graph is not None:
            # Resume while the ticket is still open (the escalation node reuses it) so the
            # paused run ends with a final message to the merchant instead of hanging forever.
            from app.api.chat import graph_config

            await graph.ainvoke(
                Command(resume={"expired": True}),
                config=graph_config(row["user_id"], row["conversation_id"], "0" * 32),
            )
        await conn.execute(
            "UPDATE handoffs SET status = 'expired' WHERE id = %s AND status = 'awaiting_human'",
            (row["id"],),
        )
        await conn.execute(
            "UPDATE conversations SET handoff_status = 'none' WHERE id = %s",
            (row["conversation_id"],),
        )
    return len(rows)


async def _retention_sweep(conn: Any) -> dict[str, int]:
    settings = get_settings()
    async with conn.transaction():
        gone = await (
            await conn.execute(
                "DELETE FROM conversations"
                " WHERE last_activity_at < now() - make_interval(days => %s)"
                " RETURNING id, user_id",
                (settings.retention_conversation_days,),
            )
        ).fetchall()
        threads = [f"{r['user_id']}:{r['id']}" for r in gone]
        if threads:
            for table in _CHECKPOINT_TABLES:
                await conn.execute(
                    f"DELETE FROM {table} WHERE thread_id = ANY(%s)",  # noqa: S608 — fixed names
                    (threads,),
                )
        aud = await conn.execute(
            "DELETE FROM audit_events WHERE ts < now() - make_interval(days => %s)",
            (settings.retention_audit_days,),
        )
    return {"conversations": len(gone), "audit_events": aud.rowcount or 0}


async def run_tick(
    pool: Pool, graph: Any = None, *, with_retention: bool | None = None
) -> dict[str, Any]:
    """``with_retention=None`` purges only in the 00:00-00:15 UTC window."""
    log = get_logger()
    async with pool.connection() as conn:
        row = await (
            await conn.execute("SELECT pg_try_advisory_lock(%s) AS got", (_LOCK_ID,))
        ).fetchone()
        if not row or not row["got"]:
            return {"skipped": True}
        try:
            sla = await _sla_sweep(conn)
            expired = await _expire_sweep(conn, graph)
            if with_retention is None:
                now = datetime.now(UTC)
                with_retention = now.hour == 0 and now.minute < 15
            retention = await _retention_sweep(conn) if with_retention else {}
            if sla or expired or retention:
                log.info("scheduler_tick", sla=sla, expired=expired, retention=retention)
            return {"sla": sla, "expired": expired, "retention": retention}
        finally:
            await conn.execute("SELECT pg_advisory_unlock(%s)", (_LOCK_ID,))


async def start(pool: Pool, graph: Any) -> asyncio.Task[None]:
    log = get_logger()

    async def _loop() -> None:
        while True:
            try:
                await run_tick(pool, graph)
            except Exception as exc:  # noqa: BLE001 — one bad tick must not kill the loop
                log.warning("scheduler_tick_error", error=type(exc).__name__)
            await asyncio.sleep(60)

    return asyncio.create_task(_loop(), name="handoff-scheduler")
