"""TOTP / 2FA enforcement by security level.

debug — skip TOTP for every account (even if 2FA is enabled).
dev   — skip only when users.require_2fa is false (current per-user flag).
prod  — 2FA is mandatory; the DB flag is ignored.
"""

from __future__ import annotations

from typing import Literal

from app.models.user import User

TwoFaMode = Literal["debug", "dev", "prod"]


def resolve_twofa_mode(app_env: str, security_level: str = "") -> TwoFaMode:
    raw = (security_level or app_env).strip().lower()
    if raw == "debug":
        return "debug"
    if raw in {"prod", "production"}:
        return "prod"
    return "dev"


def twofa_mode() -> TwoFaMode:
    from app.core.config import get_settings

    settings = get_settings()
    return resolve_twofa_mode(settings.app_env, settings.security_level)


def totp_enforced(user: User) -> bool:
    """Whether this user must satisfy TOTP (login if already enabled, agent gates)."""
    mode = twofa_mode()
    if mode == "debug":
        return False
    if mode == "prod":
        return True
    return bool(user.require_2fa)
