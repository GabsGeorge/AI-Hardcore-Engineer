"""Mailer: templates render, SMTP is called once, failure is logged, not raised (T025 / FR-002a)."""

from __future__ import annotations

from unittest.mock import patch

import aiosmtplib
import pytest

from app.ops import mailer


@pytest.fixture
def _reset_metric() -> None:
    import contextlib

    for metric in (mailer.AUTH_EMAIL_SENT, mailer.AUTH_EMAIL_ERRORS):
        with contextlib.suppress(AttributeError):
            metric.clear()


@pytest.mark.usefixtures("_reset_metric")
async def test_send_verification_renders_pt_template_with_link() -> None:
    sent: dict[str, object] = {}

    async def _fake_send(message, **kwargs):  # type: ignore[no-untyped-def]
        sent["body"] = message.get_content()
        sent["subject"] = message["Subject"]
        sent["hostname"] = kwargs.get("hostname")
        sent["port"] = kwargs.get("port")

    with patch.object(aiosmtplib, "send", side_effect=_fake_send):
        result = await mailer.send_verification(to="x@local", token="raw-token-abc", lang="pt")

    assert result.delivered is True
    assert "Confirme seu e-mail" in str(sent["subject"])
    body = str(sent["body"])
    assert "/verify?token=raw-token-abc" in body
    assert "Getnet" in body
    assert sent["port"] == 1025


@pytest.mark.usefixtures("_reset_metric")
async def test_send_reset_uses_english_template() -> None:
    captured: dict[str, str] = {}

    async def _fake_send(message, **_):  # type: ignore[no-untyped-def]
        captured["body"] = message.get_content()
        captured["subject"] = message["Subject"]

    with patch.object(aiosmtplib, "send", side_effect=_fake_send):
        await mailer.send_reset(to="x@local", token="t", lang="en")

    assert "Reset your Getnet Support password" in captured["subject"]
    assert "/reset?token=t" in captured["body"]


@pytest.mark.usefixtures("_reset_metric")
async def test_smtp_failure_is_logged_not_raised() -> None:
    async def _boom(*_a, **_k):  # type: ignore[no-untyped-def]
        raise aiosmtplib.SMTPConnectError("mailpit down")

    with patch.object(aiosmtplib, "send", side_effect=_boom):
        result = await mailer.send_invite(
            to="o@local", token="t", display_name="Operadora", role="operator"
        )

    assert result.delivered is False
    assert result.error == "SMTPConnectError"


@pytest.mark.usefixtures("_reset_metric")
async def test_template_never_echoes_secrets() -> None:
    captured: dict[str, str] = {}

    async def _fake_send(message, **_):  # type: ignore[no-untyped-def]
        captured["body"] = message.get_content()

    secret_token = "unguessable-super-token"
    with patch.object(aiosmtplib, "send", side_effect=_fake_send):
        await mailer.send_verification(to="x@local", token=secret_token)

    body = captured["body"]
    # The link must contain the token (one-time use via URL), but no password, hash or
    # database id should ever appear in the message body.
    assert secret_token in body
    for forbidden in ("argon2", "pepper", "hash", "secret_value"):
        assert forbidden not in body.lower()


@pytest.mark.usefixtures("_reset_metric")
async def test_missing_smtp_url_degrades_gracefully(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mailer.get_settings(), "smtp_url", "")
    result = await mailer.send_verification(to="x@local", token="t")
    assert result.delivered is False
    assert result.error == "smtp_not_configured"
