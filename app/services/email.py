"""Transactional email helpers (verification links)."""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


def build_verification_email(*, to_email: str, verify_url: str) -> EmailMessage:
    msg = EmailMessage()
    settings = get_settings()
    msg["Subject"] = f"Confirm your {settings.app_name} account"
    msg["From"] = settings.smtp_from
    msg["To"] = to_email
    msg.set_content(
        "Welcome to VortexSSH.\n\n"
        "Confirm your email by opening this link (valid for a limited time):\n\n"
        f"{verify_url}\n\n"
        "If you did not create this account, ignore this message.\n"
    )
    msg.add_alternative(
        f"""\
<html>
  <body style="font-family: sans-serif; background:#0a0a0a; color:#e5e7eb; padding:24px;">
    <h2 style="color:#39ff14;">Confirm your email</h2>
    <p>Welcome to VortexSSH. Click the button below to activate your account.</p>
    <p style="margin:24px 0;">
      <a href="{verify_url}"
         style="background:#39ff14;color:#0a0a0a;padding:12px 18px;text-decoration:none;font-weight:600;border-radius:6px;">
        Verify email
      </a>
    </p>
    <p style="color:#9ca3af;font-size:12px;">Or paste this URL:<br/>{verify_url}</p>
  </body>
</html>
""",
        subtype="html",
    )
    return msg


def _use_implicit_ssl(settings: Settings) -> bool:
    """Port 465 is SMTPS (implicit TLS); 587 uses STARTTLS."""
    if settings.smtp_port == 465:
        return True
    return settings.smtp_use_ssl


def _send_smtp_sync(settings: Settings, message: EmailMessage) -> None:
    if _use_implicit_ssl(settings):
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(
            settings.smtp_host,
            settings.smtp_port,
            timeout=30,
            context=context,
        ) as smtp:
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)
        return

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        smtp.ehlo()
        if settings.smtp_use_tls:
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)


async def send_verification_email(*, to_email: str, verify_url: str) -> None:
    settings = get_settings()
    message = build_verification_email(to_email=to_email, verify_url=verify_url)

    if not settings.smtp_configured:
        logger.warning(
            "SMTP not configured — verification link for %s: %s",
            to_email,
            verify_url,
        )
        return

    try:
        await asyncio.to_thread(_send_smtp_sync, settings, message)
        logger.info("Verification email sent to %s", to_email)
    except Exception:
        logger.exception("Failed to send verification email to %s", to_email)
        raise
