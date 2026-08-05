"""Telegram Bot API helpers + account linking."""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.notification import TelegramLinkCode
from app.repositories.notification import TelegramLinkRepository
from app.repositories.user import UserRepository
from app.schemas.billing import TelegramLinkResponse, TelegramStatusRead

logger = logging.getLogger(__name__)

# Cached from getMe — process-lifetime, username rarely changes.
_bot_username_cache: str | None = None


def _normalize_bot_username(raw: str) -> str:
    """Strip @ / accidental t.me URLs so deep links stay valid."""
    value = raw.strip().lstrip("@")
    lower = value.lower()
    for prefix in ("https://t.me/", "http://t.me/", "t.me/"):
        if lower.startswith(prefix):
            value = value[len(prefix) :]
            break
    return value.split("?")[0].split("/")[0].strip()


async def resolve_bot_username() -> str | None:
    """Prefer explicit TELEGRAM_BOT_USERNAME; otherwise getMe from token."""
    global _bot_username_cache
    settings = get_settings()
    if settings.telegram_bot_username.strip():
        return _normalize_bot_username(settings.telegram_bot_username)
    if _bot_username_cache:
        return _bot_username_cache
    token = settings.telegram_bot_token.strip()
    if not token:
        return None
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
        if not data.get("ok"):
            logger.warning("Telegram getMe not ok: %s", data)
            return None
        username = data.get("result", {}).get("username")
        if not username or not isinstance(username, str):
            logger.warning("Telegram getMe missing username")
            return None
        _bot_username_cache = _normalize_bot_username(username)
        return _bot_username_cache
    except Exception:
        logger.exception("Telegram getMe failed")
        return None


class TelegramService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._codes = TelegramLinkRepository(session)
        self._settings = get_settings()

    async def status_for(self, user) -> TelegramStatusRead:
        return TelegramStatusRead(
            linked=user.telegram_chat_id is not None,
            chat_id=user.telegram_chat_id,
            linked_at=user.telegram_linked_at,
            bot_username=await resolve_bot_username(),
        )

    async def create_link_code(self, user_id: UUID) -> TelegramLinkResponse:
        settings = self._settings
        if not settings.telegram_bot_token.strip():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "telegram_not_configured",
                    "message": "Telegram bot is not configured",
                },
            )
        username = await resolve_bot_username()
        if not username:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "telegram_username_unavailable",
                    "message": "Could not resolve bot username (check TELEGRAM_BOT_TOKEN)",
                },
            )
        code = secrets.token_hex(4)
        expires = datetime.now(UTC) + timedelta(minutes=settings.telegram_link_ttl_minutes)
        await self._codes.create(
            TelegramLinkCode(user_id=user_id, code=code, expires_at=expires)
        )
        await self._session.commit()
        return TelegramLinkResponse(
            code=code,
            deep_link=f"https://t.me/{username}?start={code}",
            tg_link=f"tg://resolve?domain={username}&start={code}",
            expires_at=expires,
            bot_username=username,
        )

    async def confirm_link(self, *, code: str, chat_id: str) -> None:
        row = await self._codes.get_valid_by_code(code.strip())
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "invalid_link_code",
                    "message": "Link code is invalid or expired",
                },
            )
        user = await self._users.get_by_id(row.user_id)
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "invalid_link_code", "message": "User not found"},
            )
        user.telegram_chat_id = str(chat_id)
        user.telegram_linked_at = datetime.now(UTC)
        row.used_at = datetime.now(UTC)
        await self._users.save(user)
        await self._codes.save(row)
        await self._session.commit()

    async def unlink(self, user_id: UUID) -> None:
        user = await self._users.get_by_id(user_id)
        if user is None:
            return
        user.telegram_chat_id = None
        user.telegram_linked_at = None
        await self._users.save(user)
        await self._session.commit()

    async def send_message(self, chat_id: str, text: str) -> bool:
        token = self._settings.telegram_bot_token
        if not token:
            logger.warning("TELEGRAM_BOT_TOKEN not set — skipping send")
            return False
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    url,
                    json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
                )
                if response.status_code != 200:
                    logger.warning("Telegram send failed: %s", response.text[:200])
                    return False
            return True
        except Exception:
            logger.exception("Telegram send error")
            return False
