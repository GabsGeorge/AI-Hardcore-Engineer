"""Owner data deletion (LGPD, REQ-SEC-09), feedback (REQ-OBS-05) and conversation list (US2)."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.api.auth import CurrentUser, current_user
from app.api.schemas import FeedbackRequest
from app.auth import passwords
from app.auth import repo as auth_repo
from app.auth import sessions as cookie_sessions
from app.core.config import get_settings
from app.core.errors import AppError, unauthorized
from app.db import repo
from app.db.pool import get_pool

router = APIRouter()


class ConversationSummary(BaseModel):
    id: str
    started_at: str
    last_activity_at: str
    handoff_status: Literal["none", "awaiting_human", "resolved", "expired"]
    last_message_preview: str


class ConversationList(BaseModel):
    items: list[ConversationSummary]
    next_cursor: str | None = None


@router.get("/v1/me/conversations", response_model=ConversationList)
async def my_conversations(
    user: CurrentUser = Depends(current_user),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> ConversationList:
    """List the merchant's conversations, newest first. Operator/admin see nothing here."""
    if user.role != "merchant":
        return ConversationList(items=[])
    items = await repo.list_user_conversations(
        get_pool(), user_id=user.id, limit=limit, cursor=cursor
    )
    next_cursor = items[-1].last_activity_at if len(items) == limit else None
    return ConversationList(
        items=[
            ConversationSummary(
                id=str(it.id),
                started_at=it.started_at,
                last_activity_at=it.last_activity_at,
                handoff_status=it.handoff_status,
                last_message_preview=it.last_message_preview,
            )
            for it in items
        ],
        next_cursor=next_cursor,
    )


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


class DeleteAccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=1, max_length=256)
    confirmation: Literal["EXCLUIR", "DELETE"]


@router.delete("/v1/me/account", status_code=204)
async def delete_my_account(
    body: DeleteAccountRequest,
    request: Request,
    response: Response,
    user: CurrentUser = Depends(current_user),  # noqa: ARG001 — enforces authentication
) -> Response:
    """FR-016a: wipe the auth account, conversations, feedback and merchant link, in a single
    transaction. The audit trail is preserved and pseudonymised. The ``current_user`` dep
    translates ``acc_*`` to the merchant seed id for the graph; we re-read the cookie here to
    recover the actual auth_accounts id."""
    cookie_value = request.cookies.get(cookie_sessions.COOKIE_NAME)
    if not cookie_value:
        raise unauthorized()
    try:
        claims = cookie_sessions._decode(cookie_value)  # noqa: SLF001 — safe decode-only path
    except cookie_sessions.SessionError as exc:
        raise unauthorized() from exc

    pool = get_pool()
    account = await auth_repo.get_account_by_id(pool, claims.account_id)
    if account is None:
        raise unauthorized()

    stored = await auth_repo.get_password_hash(pool, account.id)
    if stored is None or not passwords.verify_password(stored, body.password):
        raise AppError(401, "credentials_invalid", "Senha inválida.")

    graph = request.app.state.graph
    await auth_repo.delete_account_cascade(pool, account_id=account.id, graph=graph)
    for name in (cookie_sessions.COOKIE_NAME, cookie_sessions.CSRF_COOKIE_NAME):
        response.delete_cookie(name, path="/")
    response.status_code = 204
    return response


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
