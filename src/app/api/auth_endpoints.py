"""/v1/auth/* for the UI web (contract: specs/002-web-ui/contracts/auth.yaml).

Responses are deliberately generic (``GenericPending``) wherever a leak would reveal whether an
e-mail already belongs to someone: register, verify-email, reset-request and reset. Login is
the only path that distinguishes credentials from a locked account, and even then only through
HTTP status (not the message)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.api.auth import CurrentUser
from app.api.auth import current_user as current_user_dep
from app.auth import csrf as csrf_tokens
from app.auth import login_rate, one_time_tokens, passwords, repo, sessions
from app.core.errors import AppError, unauthorized
from app.db import repo as audit_repo
from app.db.pool import get_pool
from app.observability.metrics import AUTH_LOGIN, SESSIONS_ACTIVE
from app.ops import mailer

router = APIRouter(prefix="/v1/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=2, max_length=80)
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=1, max_length=256)  # strength checked by passwords module


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str


class VerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=10)


class ResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr


class ResetConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=10)
    new_password: str = Field(min_length=1, max_length=256)


class AccountOut(BaseModel):
    id: str
    role: str
    display_name: str


class LoginResponse(BaseModel):
    account: AccountOut


class SessionOut(BaseModel):
    jti: str
    issued_at: datetime
    last_seen_at: datetime
    ip: str
    user_agent: str
    current: bool


class GenericPending(BaseModel):
    status: Literal["pending"] = "pending"


class GenericOk(BaseModel):
    status: Literal["ok"] = "ok"


def _client_ip(request: Request) -> str:
    """Trust the nginx X-Real-IP header; falls back to the connection peer."""
    header = request.headers.get("x-real-ip")
    if header:
        return header.split(",")[0].strip()
    # The ASGI client should always be set; "0.0.0.0" is a defensive fallback for an edge case
    # where the transport drops the peer address, not a real listening address.
    return request.client.host if request.client else "0.0.0.0"  # noqa: S104


def _is_secure(request: Request) -> bool:
    """``Secure`` cookie attribute. Behind nginx we trust ``X-Forwarded-Proto``."""
    return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"


def _set_session_cookies(response: Response, request: Request, token: str, csrf: str) -> None:
    attrs = sessions.cookie_attributes(secure=_is_secure(request))
    response.set_cookie(sessions.COOKIE_NAME, token, **attrs)
    public = dict(attrs)
    public["httponly"] = False  # JS reads the csrf cookie to echo it in X-CSRF-Token
    response.set_cookie(sessions.CSRF_COOKIE_NAME, csrf, **public)


def _clear_session_cookies(response: Response) -> None:
    for name in (sessions.COOKIE_NAME, sessions.CSRF_COOKIE_NAME):
        response.delete_cookie(name, path="/")


async def _require_csrf(request: Request) -> None:
    cookie_value = request.cookies.get(sessions.CSRF_COOKIE_NAME)
    header_value = request.headers.get(csrf_tokens.HEADER_NAME)
    if not csrf_tokens.verify(cookie_value, header_value):
        raise AppError(403, "csrf_failed", "Missing or invalid CSRF token.")


@router.post("/register", status_code=202, response_model=GenericPending)
async def register(body: RegisterRequest, request: Request) -> GenericPending:
    """Autocadastro só cria lojista; operador/admin saem do convite admin (FR-001).

    Reutiliza a mesma resposta para e-mail novo e existente (FR-004); o pedido ``duplicate``
    ainda vira linha de auditoria para análise forense.
    """
    pool = get_pool()
    try:
        passwords.check_strength(body.password)
    except passwords.WeakPasswordError as exc:
        raise AppError(422, "weak_password", str(exc)) from exc

    existing = await repo.get_account_by_email(pool, body.email)
    if existing is None:
        account = await repo.create_account(
            pool, email=body.email, display_name=body.display_name, role="merchant"
        )
        await repo.set_password(pool, account.id, passwords.hash_password(body.password))
        token = await one_time_tokens.mint(pool, account_id=account.id, purpose="verify_email")
        await mailer.send_verification(to=body.email, token=token)
        await _audit(
            request,
            actor_id=account.id,
            action="account_registered",
            target=f"account:{account.id}",
        )
    else:
        await _audit(
            request,
            actor_id="anonymous",
            action="account_registered_duplicate",
            target=f"email:{existing.email_lower}",
            outcome="denied",
        )
    return GenericPending()


async def _audit(
    request: Request,
    *,
    actor_id: str,
    action: str,
    target: str,
    outcome: str = "allowed",
    actor_role: str = "merchant",
) -> None:
    trace_id = getattr(request.state, "trace_id", "")
    await audit_repo.insert_audit_event(
        get_pool(),
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        target=target,
        outcome=outcome,
        trace_id=trace_id,
    )


@router.post("/verify-email", response_model=GenericOk)
async def verify_email(body: VerifyRequest, request: Request) -> GenericOk:
    account_id = await one_time_tokens.consume(get_pool(), token=body.token, purpose="verify_email")
    if account_id is None:
        raise AppError(410, "token_invalid", "Link inválido ou expirado.")
    await repo.activate_account(get_pool(), account_id)
    await _audit(
        request, actor_id=account_id, action="email_verified", target=f"account:{account_id}"
    )
    return GenericOk()


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request, response: Response) -> LoginResponse:
    pool = get_pool()
    redis = request.app.state.redis
    ip = _client_ip(request)
    email_lower = body.email.strip().lower()

    gate = await login_rate.before_login(redis, email_lower=email_lower, ip=ip)
    if gate.decision != "allow":
        AUTH_LOGIN.labels(gate.decision).inc()
        await audit_repo.insert_audit_event(
            pool,
            actor_id="anonymous",
            actor_role="unknown",
            action="login_locked" if gate.decision == "locked" else "login_rate_limited",
            target=f"email:{email_lower}",
            outcome="denied",
            trace_id=getattr(request.state, "trace_id", ""),
        )
        status = 423 if gate.decision == "locked" else 429
        headers = {"Retry-After": str(gate.retry_after_s)}
        raise AppError(status, "login_denied", "Credenciais inválidas.", headers=headers)

    account = await repo.get_account_by_email(pool, body.email)
    if account is None:
        await login_rate.on_failure(redis, email_lower=email_lower, ip=ip)
        await audit_repo.insert_audit_event(
            pool,
            actor_id="anonymous",
            actor_role="unknown",
            action="login_failed",
            target=f"email:{email_lower}",
            outcome="denied",
            trace_id=getattr(request.state, "trace_id", ""),
        )
        AUTH_LOGIN.labels("unknown_account").inc()
        raise AppError(401, "login_failed", "Credenciais inválidas.")

    stored = await repo.get_password_hash(pool, account.id)
    if stored is None or not passwords.verify_password(stored, body.password):
        await login_rate.on_failure(redis, email_lower=email_lower, ip=ip)
        await audit_repo.insert_audit_event(
            pool,
            actor_id=account.id,
            actor_role=account.role,
            action="login_failed",
            target=f"account:{account.id}",
            outcome="denied",
            trace_id=getattr(request.state, "trace_id", ""),
        )
        AUTH_LOGIN.labels("bad_password").inc()
        raise AppError(401, "login_failed", "Credenciais inválidas.")

    if account.status != "active":
        AUTH_LOGIN.labels(account.status).inc()
        raise AppError(401, "login_failed", "Credenciais inválidas.")

    await login_rate.on_success(redis, email_lower=email_lower, ip=ip)
    user_agent = request.headers.get("user-agent", "")[:200] or "unknown"
    token, _claims = await sessions.issue(
        pool, account_id=account.id, role=account.role, ip=ip, user_agent=user_agent
    )
    csrf = csrf_tokens.new_token()
    _set_session_cookies(response, request, token, csrf)
    AUTH_LOGIN.labels("ok").inc()
    SESSIONS_ACTIVE.inc()
    await _audit(
        request,
        actor_id=account.id,
        actor_role=account.role,
        action="login_ok",
        target=f"account:{account.id}",
    )
    return LoginResponse(
        account=AccountOut(id=account.id, role=account.role, display_name=account.display_name)
    )


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response) -> Response:
    await _require_csrf(request)
    cookie_value = request.cookies.get(sessions.COOKIE_NAME)
    if cookie_value:
        try:
            claims = sessions._decode(cookie_value)  # noqa: SLF001 — safe decode-only path
        except sessions.SessionError:
            claims = None
        if claims is not None:
            await sessions.revoke(get_pool(), claims.jti)
            await _audit(
                request,
                actor_id=claims.account_id,
                action="logout",
                target=f"account:{claims.account_id}",
            )
    _clear_session_cookies(response)
    response.status_code = 204
    return response


@router.post("/password/reset-request", status_code=202, response_model=GenericPending)
async def reset_request(body: ResetRequest, request: Request) -> GenericPending:
    pool = get_pool()
    account = await repo.get_account_by_email(pool, body.email)
    if account is not None and account.status != "deactivated":
        token = await one_time_tokens.mint(pool, account_id=account.id, purpose="password_reset")
        await mailer.send_reset(to=body.email, token=token)
        await _audit(
            request,
            actor_id=account.id,
            actor_role=account.role,
            action="password_reset_requested",
            target=f"account:{account.id}",
        )
    return GenericPending()


@router.post("/password/reset", response_model=GenericOk)
async def reset_confirm(body: ResetConfirm, request: Request) -> GenericOk:
    account_id = await one_time_tokens.consume(
        get_pool(), token=body.token, purpose="password_reset"
    )
    if account_id is None:
        raise AppError(410, "token_invalid", "Link inválido ou expirado.")
    try:
        hashed = passwords.hash_password(body.new_password)
    except passwords.WeakPasswordError as exc:
        raise AppError(422, "weak_password", str(exc)) from exc
    await repo.set_password(get_pool(), account_id, hashed)
    revoked = await sessions.revoke_all(get_pool(), account_id)
    await _audit(
        request,
        actor_id=account_id,
        action="password_reset_completed",
        target=f"account:{account_id}",
    )
    _ = revoked  # metric wired in Phase 2b observability sweep
    return GenericOk()


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(
    request: Request, user: CurrentUser = Depends(current_user_dep)
) -> list[SessionOut]:
    cookie_value = request.cookies.get(sessions.COOKIE_NAME)
    current_jti: str | None = None
    if cookie_value:
        try:
            current_jti = sessions._decode(cookie_value).jti  # noqa: SLF001
        except sessions.SessionError:
            current_jti = None
    pool = get_pool()
    async with pool.connection() as conn:
        rows = await (
            await conn.execute(
                "SELECT jti, issued_at, last_seen_at, ip, user_agent FROM auth_sessions"
                " WHERE account_id = %s AND revoked_at IS NULL ORDER BY last_seen_at DESC",
                (user.id,),
            )
        ).fetchall()
    return [
        SessionOut(
            jti=r["jti"],
            issued_at=r["issued_at"],
            last_seen_at=r["last_seen_at"],
            ip=str(r["ip"]),
            user_agent=r["user_agent"],
            current=r["jti"] == current_jti,
        )
        for r in rows
    ]


@router.delete("/sessions", status_code=204)
async def revoke_others(
    request: Request, user: CurrentUser = Depends(current_user_dep)
) -> Response:
    await _require_csrf(request)
    cookie_value = request.cookies.get(sessions.COOKIE_NAME) or ""
    try:
        current_jti = sessions._decode(cookie_value).jti  # noqa: SLF001
    except sessions.SessionError as exc:
        raise unauthorized() from exc
    await sessions.revoke_all(get_pool(), user.id, except_jti=current_jti)
    return Response(status_code=204)


@router.get("/me", response_model=AccountOut)
async def me(user: CurrentUser = Depends(current_user_dep)) -> AccountOut:
    """Front-end hits this once per session to know the role and the display name."""
    account = await repo.get_account_by_id(get_pool(), user.id)
    if account is None:
        # Legacy Bearer token for a seeded user: there is no auth_accounts row to project.
        return AccountOut(id=user.id, role=user.role, display_name=user.id)
    return AccountOut(id=account.id, role=account.role, display_name=account.display_name)
