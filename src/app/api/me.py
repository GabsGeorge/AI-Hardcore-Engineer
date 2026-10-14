"""Endpoints do usuário: exclusão de dados (LGPD) e feedback (REQ-SEC-09, REQ-OBS-05)."""

from __future__ import annotations

import contextlib
import hashlib
import hmac
from typing import Any

from fastapi import APIRouter, Depends, Request

from app.api.auth import CurrentUser, current_user
from app.api.schemas import FeedbackRequest
from app.core.config import get_settings
from app.db import repo
from app.db.pool import get_pool

router = APIRouter()


def _pseudonymize(user_id: str) -> str:
    """Marcador irreversível para a auditoria pós-exclusão: ``deleted:<hmac>``."""
    secret = get_settings().jwt_secret.get_secret_value().encode("utf-8")
    tag = hmac.new(secret, user_id.encode("utf-8"), hashlib.sha256).hexdigest()[:16]
    return f"deleted:{tag}"


@router.delete("/v1/me/data", status_code=200)
async def delete_my_data(
    request: Request, user: CurrentUser = Depends(current_user)
) -> dict[str, Any]:
    """Apaga conversas, handoffs e checkpoints do dono; pseudonimiza a auditoria.

    Fluxo:
    - Para cada thread do usuário, remove o checkpoint via ``adelete_thread`` (LangGraph).
    - Remove rows em ``conversations`` e ``handoffs`` (CASCADE no FK derruba o resto).
    - Reescreve ``audit_log.actor_id`` para ``deleted:<hmac>`` (não removemos a auditoria —
      ela é pseudonimizada, atende LGPD mantendo trilha de segurança).
    """
    pool = get_pool()
    graph = request.app.state.graph
    thread_ids = await repo.list_user_thread_ids(pool, user.id)

    if graph is not None:
        for thread_id in thread_ids:
            # Um checkpoint ausente não pode bloquear a exclusão dos dados.
            with contextlib.suppress(Exception):
                await graph.checkpointer.adelete_thread(thread_id)

    pseudonym = _pseudonymize(user.id)
    counts = await repo.delete_user_data(pool, user.id, pseudonym=pseudonym)
    return {"deleted": counts, "pseudonym": pseudonym}


@router.post("/v1/feedback", status_code=202)
async def submit_feedback(
    body: FeedbackRequest, request: Request, user: CurrentUser = Depends(current_user)
) -> dict[str, str]:
    """Avaliação +1/-1 ligada ao ``trace_id`` para melhoria contínua (REQ-OBS-05)."""
    await repo.insert_feedback(
        get_pool(),
        user_id=user.id,
        trace_id=body.trace_id,
        rating=body.rating,
        comment=body.comment,
    )
    return {"status": "accepted"}
