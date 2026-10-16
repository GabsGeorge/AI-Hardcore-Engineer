"""SMTP sender for the three transactional e-mails of the UI web: confirm e-mail, reset
password, invite operator/admin.

Delivery is best-effort: FR-002a forbids leaking whether an account exists, so the callers
treat an SMTP failure as a non-error and get back ``True``/``False`` instead of exceptions.
URLs are built from ``WEB_BASE_URL`` so the link is clickable in Mailpit during local dev.
"""

from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Literal
from urllib.parse import quote, urlsplit

import aiosmtplib

from app.auth.one_time_tokens import Purpose
from app.core.config import get_settings
from app.observability.logging import get_logger
from app.observability.metrics import AUTH_EMAIL_ERRORS, AUTH_EMAIL_SENT

Language = Literal["pt", "en"]
_TEMPLATES_DIR = Path(__file__).resolve().parent / "mail_templates"


@dataclass(frozen=True)
class EmailResult:
    delivered: bool
    error: str | None = None


def _render(name: str, lang: Language, **vars: str) -> str:
    text = (_TEMPLATES_DIR / f"{name}.{lang}.txt").read_text(encoding="utf-8")
    for key, value in vars.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def _link(path: str, token: str) -> str:
    base = get_settings().web_base_url.rstrip("/")
    return f"{base}{path}?token={quote(token, safe='')}"


async def _send(*, to: str, subject: str, body: str, kind: str) -> EmailResult:
    settings = get_settings()
    if not settings.smtp_url:
        get_logger().warning("mail_disabled", kind=kind)
        return EmailResult(delivered=False, error="smtp_not_configured")

    parsed = urlsplit(settings.smtp_url)
    message = EmailMessage()
    message["From"] = f"Atendimento Getnet <noreply@{parsed.hostname or 'getnet.local'}>"
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    try:
        await aiosmtplib.send(
            message,
            hostname=parsed.hostname or "mailpit",
            port=parsed.port or 1025,
            username=parsed.username or None,
            password=parsed.password or None,
            use_tls=parsed.scheme == "smtps",
            start_tls=False,
            timeout=10,
        )
    except Exception as exc:  # noqa: BLE001 — delivery stays best-effort (FR-002a)
        AUTH_EMAIL_ERRORS.labels(kind).inc()
        get_logger().warning("mail_error", kind=kind, error=type(exc).__name__)
        return EmailResult(delivered=False, error=type(exc).__name__)
    AUTH_EMAIL_SENT.labels(kind).inc()
    return EmailResult(delivered=True)


async def send_verification(*, to: str, token: str, lang: Language = "pt") -> EmailResult:
    link = _link("/verify", token)
    subject = {
        "pt": "Confirme seu e-mail no Atendimento Getnet",
        "en": "Confirm your e-mail at Getnet Support",
    }[lang]
    body = _render("verify_email", lang, link=link)
    return await _send(to=to, subject=subject, body=body, kind="verify_email")


async def send_reset(*, to: str, token: str, lang: Language = "pt") -> EmailResult:
    link = _link("/reset", token)
    subject = {
        "pt": "Redefinir senha do Atendimento Getnet",
        "en": "Reset your Getnet Support password",
    }[lang]
    body = _render("password_reset", lang, link=link)
    return await _send(to=to, subject=subject, body=body, kind="password_reset")


async def send_invite(
    *, to: str, token: str, display_name: str, role: str, lang: Language = "pt"
) -> EmailResult:
    link = _link("/invite", token)
    subject = {
        "pt": "Convite para o Atendimento Getnet",
        "en": "Invitation to Getnet Support",
    }[lang]
    body = _render("invite", lang, link=link, display_name=display_name, role=role)
    return await _send(to=to, subject=subject, body=body, kind="invite")


def purpose_sender(purpose: Purpose) -> str:
    return {
        "verify_email": "send_verification",
        "password_reset": "send_reset",
        "invite": "send_invite",
    }[purpose]
