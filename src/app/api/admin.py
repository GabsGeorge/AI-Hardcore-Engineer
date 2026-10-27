"""Admin endpoints (US6): manage accounts, link merchants, view the queue and the audit trail.

Every route requires the ``admin`` role via ``require_role``. Writes also require the CSRF
double-submit (same policy used by the auth endpoints). Side-effects that matter — invites,
deactivations, links — produce an audit row with ``actor_id`` set to the acting admin.

Contract: specs/002-web-ui/contracts/admin.yaml.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.api.auth import CurrentUser, require_role
from app.auth import csrf as csrf_tokens
from app.auth import one_time_tokens
from app.auth import repo as auth_repo
from app.auth import sessions as cookie_sessions
from app.core.errors import AppError
from app.db import repo as db_repo
from app.db.pool import get_pool
from app.ops import mailer

router = APIRouter(prefix="/v1/admin", tags=["admin"])

_ADMIN = require_role("admin")


class InviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=2, max_length=80)
    email: EmailStr = Field(max_length=254)
    role: Literal["operator", "admin"]


class LinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: str = Field(min_length=4, max_length=64)


class AccountOut(BaseModel):
    id: str
    email: str
    display_name: str
    role: Literal["merchant", "operator", "admin"]
    status: Literal["pending", "active", "locked", "deactivated"]
    linked_merchant_id: str | None = None


class QueueOverview(BaseModel):
    awaiting_human: int
    sla_breached_today: int
    expired_today: int


class AuditEventOut(BaseModel):
    ts: datetime
    actor_id: str
    actor_role: str
    action: str
    target: str
    outcome: Literal["allowed", "denied", "error"]
    trace_id: str


async def _require_csrf(request: Request) -> None:
    cookie_value = request.cookies.get(cookie_sessions.CSRF_COOKIE_NAME)
    header_value = request.headers.get(csrf_tokens.HEADER_NAME)
    if not csrf_tokens.verify(cookie_value, header_value):
        raise AppError(403, "csrf_failed", "Missing or invalid CSRF token.")


async def _audit(
    request: Request,
    *,
    actor_id: str,
    action: str,
    target: str,
    outcome: str = "allowed",
    metadata: dict[str, Any] | None = None,
) -> None:
    trace_id = getattr(request.state, "trace_id", "")
    await db_repo.insert_audit_event(
        get_pool(),
        actor_id=actor_id,
        actor_role="admin",
        action=action,
        target=target,
        outcome=outcome,
        trace_id=trace_id,
        metadata=metadata,
    )


@router.get("/accounts", response_model=list[AccountOut])
async def list_accounts(
    role: Literal["merchant", "operator", "admin"] | None = Query(default=None),
    status: Literal["pending", "active", "locked", "deactivated"] | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    _user: CurrentUser = Depends(_ADMIN),
) -> list[AccountOut]:
    rows = await auth_repo.list_accounts(get_pool(), role=role, status=status, limit=limit)
    return [
        AccountOut(
            id=r.id,
            email=r.email_lower,
            display_name=r.display_name,
            role=r.role,
            status=r.status,
            linked_merchant_id=r.linked_merchant_id,
        )
        for r in rows
    ]


@router.post("/accounts", status_code=202)
async def invite(
    body: InviteRequest, request: Request, user: CurrentUser = Depends(_ADMIN)
) -> dict[str, str]:
    """Creates a ``pending`` account for the invitee and e-mails them a one-time link.

    A duplicate e-mail returns the same 202 as a fresh invite — the SPA cannot tell them
    apart, which keeps enumeration shut (FR-004 extends to invites).
    """
    await _require_csrf(request)
    pool = get_pool()
    existing = await auth_repo.get_account_by_email(pool, body.email)
    if existing is None:
        account = await auth_repo.create_account(
            pool,
            email=body.email,
            display_name=body.display_name,
            role=body.role,
            status="pending",
        )
        token = await one_time_tokens.mint(pool, account_id=account.id, purpose="invite")
        await mailer.send_invite(
            to=body.email, token=token, display_name=body.display_name, role=body.role
        )
        await _audit(
            request,
            actor_id=user.id,
            action="invite_sent",
            target=f"account:{account.id}",
            metadata={"role": body.role},
        )
    else:
        await _audit(
            request,
            actor_id=user.id,
            action="invite_duplicate",
            target=f"email:{existing.email_lower}",
            outcome="denied",
        )
    return {"status": "pending"}


@router.post("/accounts/{account_id}/activate", status_code=204)
async def activate(
    account_id: str, request: Request, user: CurrentUser = Depends(_ADMIN)
) -> Response:
    await _require_csrf(request)
    pool = get_pool()
    acc = await auth_repo.get_account_by_id(pool, account_id)
    if acc is None:
        raise AppError(404, "not_found", "Conta não encontrada.")
    if acc.status != "deactivated":
        raise AppError(409, "already_active", "A conta já está ativa.")
    await auth_repo.set_status(pool, account_id, "active")
    await _audit(
        request, actor_id=user.id, action="account_activated", target=f"account:{account_id}"
    )
    return Response(status_code=204)


@router.post("/accounts/{account_id}/deactivate", status_code=204)
async def deactivate(
    account_id: str, request: Request, user: CurrentUser = Depends(_ADMIN)
) -> Response:
    await _require_csrf(request)
    if account_id == user.id:
        # Avoid locking the admin out of the system from the SPA.
        raise AppError(409, "cannot_deactivate_self", "Você não pode desativar sua própria conta.")
    pool = get_pool()
    acc = await auth_repo.get_account_by_id(pool, account_id)
    if acc is None:
        raise AppError(404, "not_found", "Conta não encontrada.")
    await auth_repo.set_status(pool, account_id, "deactivated")
    revoked = await cookie_sessions.revoke_all(pool, account_id)
    await _audit(
        request,
        actor_id=user.id,
        action="account_deactivated",
        target=f"account:{account_id}",
        metadata={"revoked_sessions": revoked},
    )
    return Response(status_code=204)


@router.post("/merchants/{merchant_user_id}/link", status_code=204)
async def link_merchant(
    merchant_user_id: str,
    body: LinkRequest,
    request: Request,
    user: CurrentUser = Depends(_ADMIN),
) -> Response:
    """Idempotent for the same (merchant, account) pair; a second account on the same merchant
    returns 409 so the SPA shows the conflict (FR-021)."""
    await _require_csrf(request)
    pool = get_pool()
    acc = await auth_repo.get_account_by_id(pool, body.account_id)
    if acc is None or acc.role != "merchant":
        raise AppError(409, "invalid_account", "Conta inválida para vínculo.")
    linked = await auth_repo.link_merchant(
        pool, merchant_user_id=merchant_user_id, account_id=body.account_id
    )
    if not linked:
        await _audit(
            request,
            actor_id=user.id,
            action="merchant_link_conflict",
            target=f"merchant:{merchant_user_id}",
            outcome="denied",
        )
        raise AppError(409, "merchant_already_linked", "Estabelecimento já ligado a outra conta.")
    await _audit(
        request,
        actor_id=user.id,
        action="merchant_linked",
        target=f"merchant:{merchant_user_id}",
        metadata={"account_id": body.account_id},
    )
    return Response(status_code=204)


@router.delete("/merchants/{merchant_user_id}/link", status_code=204)
async def unlink_merchant(
    merchant_user_id: str, request: Request, user: CurrentUser = Depends(_ADMIN)
) -> Response:
    await _require_csrf(request)
    await auth_repo.unlink_merchant(get_pool(), merchant_user_id)
    await _audit(
        request,
        actor_id=user.id,
        action="merchant_unlinked",
        target=f"merchant:{merchant_user_id}",
    )
    return Response(status_code=204)


@router.get("/queue", response_model=QueueOverview)
async def queue_overview(_user: CurrentUser = Depends(_ADMIN)) -> QueueOverview:
    counts = await db_repo.queue_overview(get_pool())
    return QueueOverview(**counts)


@router.get("/audit", response_model=list[AuditEventOut])
async def audit_list(
    action: str | None = Query(default=None, max_length=120),
    since: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    _user: CurrentUser = Depends(_ADMIN),
) -> list[AuditEventOut]:
    rows = await db_repo.list_audit_events(get_pool(), action=action, since=since, limit=limit)
    return [AuditEventOut(**r) for r in rows]
