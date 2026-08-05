from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, TelegramLinkCode, UserNotificationSettings


class NotificationSettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self, user_id: UUID) -> UserNotificationSettings:
        result = await self._session.execute(
            select(UserNotificationSettings).where(UserNotificationSettings.user_id == user_id)
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return row
        row = UserNotificationSettings(user_id=user_id)
        self._session.add(row)
        await self._session.flush()
        return row

    async def save(self, settings: UserNotificationSettings) -> UserNotificationSettings:
        self._session.add(settings)
        await self._session.flush()
        return settings


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user(
        self,
        user_id: UUID,
        *,
        unread_only: bool = False,
        limit: int = 50,
    ) -> list[Notification]:
        query = (
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
        if unread_only:
            query = query.where(Notification.read_at.is_(None))
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_by_id(self, notification_id: UUID, user_id: UUID) -> Notification | None:
        result = await self._session.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, notification: Notification) -> Notification | None:
        """Insert notification; return None on dedupe conflict."""
        from sqlalchemy.exc import IntegrityError

        self._session.add(notification)
        try:
            await self._session.flush()
        except IntegrityError:
            await self._session.rollback()
            return None
        return notification

    async def mark_read(self, notification: Notification) -> Notification:
        notification.read_at = datetime.now(UTC)
        self._session.add(notification)
        await self._session.flush()
        return notification

    async def mark_all_read(self, user_id: UUID) -> int:
        result = await self._session.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
            .values(read_at=datetime.now(UTC))
        )
        await self._session.flush()
        return int(result.rowcount or 0)


class TelegramLinkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, row: TelegramLinkCode) -> TelegramLinkCode:
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_valid_by_code(self, code: str) -> TelegramLinkCode | None:
        now = datetime.now(UTC)
        result = await self._session.execute(
            select(TelegramLinkCode).where(
                TelegramLinkCode.code == code,
                TelegramLinkCode.used_at.is_(None),
                TelegramLinkCode.expires_at > now,
            )
        )
        return result.scalar_one_or_none()

    async def save(self, row: TelegramLinkCode) -> TelegramLinkCode:
        self._session.add(row)
        await self._session.flush()
        return row
