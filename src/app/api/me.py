"""Owner data deletion (LGPD, REQ-SEC-09) and feedback (REQ-OBS-05)."""

from __future__ import annotations

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
    secret = get_settings().jwt_secret.get_secret_value().encode("utf-8")
    return "deleted:" + hmac.new(secret, user_id.encode("utf-8"), hashlib.sha256).hexdigest()[:16]


@router.delete("/v1/me/data", status_code=200)
async def delete_my_data(
    request: Request, user: CurrentUser = Depends(current_user)
) -> dict[str, Any]:
    """Audit rows are pseudonymised, not deleted: the security trail must survive."""
    pool = get_pool()
    graph = request.app.state.graph
    if graph is not None:
        # No error swallowing: a failure here must not be reported as a successful deletion.
        # Deleting an absent thread is a no-op, so a client retry is safe.
        for thread_id in await repo.list_user_thread_ids(pool, user.id):
            await graph.checkpointer.adelete_thread(thread_id)
    pseudonym = _pseudonymize(user.id)
    counts = await repo.delete_user_data(pool, user.id, pseudonym=pseudonym)
    return {"deleted": counts, "pseudonym": pseudonym}


@router.post("/v1/feedback", status_code=202)
async def submit_feedback(
    body: FeedbackRequest, request: Request, user: CurrentUser = Depends(current_user)
) -> dict[str, str]:
    await repo.insert_feedback(
        get_pool(),
        user_id=user.id,
        trace_id=body.trace_id,
        rating=body.rating,
        comment=body.comment,
    )
    return {"status": "accepted"}
