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


class TelegramService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._codes = TelegramLinkRepository(session)
        self._settings = get_settings()

    def status_for(self, user) -> TelegramStatusRead:
        return TelegramStatusRead(
            linked=user.telegram_chat_id is not None,
            chat_id=user.telegram_chat_id,
            linked_at=user.telegram_linked_at,
            bot_username=self._settings.telegram_bot_username or None,
        )

    async def create_link_code(self, user_id: UUID) -> TelegramLinkResponse:
        settings = self._settings
        if not settings.telegram_bot_username:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "telegram_not_configured",
                    "message": "Telegram bot is not configured",
                },
            )
        code = secrets.token_hex(4)
        expires = datetime.now(UTC) + timedelta(minutes=settings.telegram_link_ttl_minutes)
        await self._codes.create(
            TelegramLinkCode(user_id=user_id, code=code, expires_at=expires)
        )
        await self._session.commit()
        username = settings.telegram_bot_username.lstrip("@")
        return TelegramLinkResponse(
            code=code,
            deep_link=f"https://t.me/{username}?start={code}",
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
