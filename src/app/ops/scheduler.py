"""Tarefa periódica de SLA, expiração e expurgo (REQ-HITL-05, REQ-SEC-09).

Roda a cada 60 s, segurado por ``pg_try_advisory_lock`` para garantir uma única instância ativa
em um cluster multi-réplica. Em cada tick:

1. **SLA warning**: tickets ``awaiting_human`` com ``sla_due_at`` vencido e ainda
   ``priority=normal`` são promovidos a ``high``.
2. **Expiração**: tickets ``awaiting_human`` com ``expires_at`` vencido viram ``expired``;
   a conversa correspondente volta a ``none``.
3. **Expurgo** (uma vez por dia, janela 00:00–00:15 UTC):
   - conversas inativas há mais de ``retention_conversation_days``;
   - eventos de auditoria mais antigos que ``retention_audit_days``.

O scheduler expõe ``run_tick(pool)`` para que a suíte dispare um tick direto e asserte os efeitos
sem precisar esperar o relógio real.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings
from app.db.pool import Pool
from app.observability.logging import get_logger

_LOCK_ID = 7_300_914_257  # arbitrário mas estável; o único consumidor deste cadeado é o scheduler.


async def _sla_sweep(conn: Any) -> int:
    """Promove tickets com SLA estourado a prioridade alta."""
    cur = await conn.execute(
        "UPDATE handoffs SET priority = 'high'"
        " WHERE status = 'awaiting_human' AND priority = 'normal' AND sla_due_at < now()"
    )
    return cur.rowcount or 0


async def _expire_sweep(conn: Any) -> int:
    """Vence tickets expirados e devolve a conversa para o estado neutro."""
    cur = await conn.execute(
        "UPDATE handoffs SET status = 'expired'"
        " WHERE status = 'awaiting_human' AND expires_at < now()"
        " RETURNING conversation_id"
    )
    rows = await cur.fetchall()
    for row in rows:
        await conn.execute(
            "UPDATE conversations SET handoff_status = 'none' WHERE id = %s",
            (row["conversation_id"],),
        )
    return len(rows)


async def _retention_sweep(conn: Any) -> dict[str, int]:
    """Expurga conversas e auditoria velhas; chamada só uma vez por dia (REQ-SEC-09)."""
    settings = get_settings()
    conv = await conn.execute(
        "DELETE FROM conversations WHERE last_activity_at < now() - make_interval(days => %s)",
        (settings.retention_conversation_days,),
    )
    aud = await conn.execute(
        "DELETE FROM audit_events WHERE ts < now() - make_interval(days => %s)",
        (settings.retention_audit_days,),
    )
    return {"conversations": conv.rowcount or 0, "audit_events": aud.rowcount or 0}


async def run_tick(pool: Pool, *, with_retention: bool | None = None) -> dict[str, Any]:
    """Um tick do scheduler. ``with_retention=None`` deixa a decisão com a janela horária;
    passar ``True`` força o expurgo (útil nos testes)."""
    log = get_logger()
    async with pool.connection() as conn:
        cur = await conn.execute("SELECT pg_try_advisory_lock(%s) AS got", (_LOCK_ID,))
        row = await cur.fetchone()
        if not row or not row["got"]:
            log.info("scheduler_skip", reason="lock_held")
            return {"skipped": True}
        try:
            sla = await _sla_sweep(conn)
            expired = await _expire_sweep(conn)
            if with_retention is None:
                now = datetime.now(UTC)
                with_retention = now.hour == 0 and now.minute < 15
            retention = await _retention_sweep(conn) if with_retention else {}
            if sla or expired or retention:
                log.info("scheduler_tick", sla=sla, expired=expired, retention=retention)
            return {"sla": sla, "expired": expired, "retention": retention}
        finally:
            await conn.execute("SELECT pg_advisory_unlock(%s)", (_LOCK_ID,))


async def start(pool: Pool) -> asyncio.Task[None]:
    """Loop em background com intervalo de 60 s. O lifespan cancela a task no shutdown."""
    log = get_logger()

    async def _loop() -> None:
        while True:
            try:
                await run_tick(pool)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — telemetria defensiva
                log.warning("scheduler_tick_error", error=type(exc).__name__)
            await asyncio.sleep(60)

    return asyncio.create_task(_loop(), name="handoff-scheduler")
