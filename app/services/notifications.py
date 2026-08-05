"""In-app notifications + multi-channel activity / billing alerts."""

from __future__ import annotations

import logging
import secrets
from datetime import date
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import KIND_SETTING_ATTR, NotificationKind
from app.models.host import Host
from app.models.notification import Notification, UserNotificationSettings
from app.models.user import User
from app.repositories.notification import NotificationRepository, NotificationSettingsRepository
from app.repositories.user import UserRepository
from app.schemas.billing import NotificationSettingsUpdate
from app.services.email import send_mail
from app.services.telegram import TelegramService

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._notifications = NotificationRepository(session)
        self._settings = NotificationSettingsRepository(session)
        self._users = UserRepository(session)
        self._telegram = TelegramService(session)

    async def get_settings(self, user_id: UUID) -> UserNotificationSettings:
        settings = await self._settings.get_or_create(user_id)
        await self._session.commit()
        return settings

    async def update_settings(
        self,
        user_id: UUID,
        payload: NotificationSettingsUpdate,
    ) -> UserNotificationSettings:
        settings = await self._settings.get_or_create(user_id)
        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(settings, key, value)
        await self._settings.save(settings)
        await self._session.commit()
        return settings

    async def list_notifications(
        self,
        user_id: UUID,
        *,
        unread_only: bool = False,
        limit: int = 50,
    ) -> list[Notification]:
        return await self._notifications.list_for_user(
            user_id, unread_only=unread_only, limit=limit
        )

    async def mark_read(self, user_id: UUID, notification_id: UUID) -> Notification:
        from fastapi import HTTPException, status

        row = await self._notifications.get_by_id(notification_id, user_id)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "notification_not_found", "message": "Not found"},
            )
        updated = await self._notifications.mark_read(row)
        await self._session.commit()
        return updated

    async def mark_all_read(self, user_id: UUID) -> int:
        count = await self._notifications.mark_all_read(user_id)
        await self._session.commit()
        return count

    async def emit_activity(
        self,
        user: User,
        *,
        kind: NotificationKind | str,
        title: str,
        body: str,
        host_id: UUID | None = None,
        dedupe_key: str | None = None,
        payload: dict | None = None,
        settings: UserNotificationSettings | None = None,
    ) -> None:
        """Fan-out to enabled channels if the per-event toggle is on."""
        kind_value = str(kind)
        settings = settings or await self._settings.get_or_create(user.id)
        attr = KIND_SETTING_ATTR.get(kind_value)
        if attr is not None and not bool(getattr(settings, attr, True)):
            logger.info(
                "Skip notify kind=%s user=%s — event toggle %s is off",
                kind_value,
                user.email,
                attr,
            )
            return

        key = dedupe_key or secrets.token_hex(8)
        delivered: list[str] = []

        if settings.in_app_enabled or settings.client_enabled:
            row = await self._create_inbox(
                user_id=user.id,
                host_id=host_id,
                kind=kind_value,
                title=title,
                body=body,
                dedupe_key=key,
                payload={
                    **(payload or {}),
                    "channels": {
                        "in_app": settings.in_app_enabled,
                        "client": settings.client_enabled,
                    },
                },
            )
            if row is not None:
                delivered.append("inbox")

        if settings.email_enabled:
            try:
                await send_mail(
                    to_email=user.email,
                    subject=f"[Vortex] {title}",
                    text=body,
                    html=(
                        f"<p style='font-family:sans-serif;color:#e5e7eb;background:#0a0a0a;"
                        f"padding:16px'>{body}</p>"
                    ),
                )
                delivered.append("email")
            except Exception:
                logger.exception("Activity email failed for %s (%s)", user.email, kind_value)
        else:
            logger.info("Skip email kind=%s user=%s — email_enabled=false", kind_value, user.email)

        if not settings.telegram_enabled:
            logger.info(
                "Skip telegram kind=%s user=%s — telegram_enabled=false",
                kind_value,
                user.email,
            )
        elif not user.telegram_chat_id:
            logger.warning(
                "Skip telegram kind=%s user=%s — telegram not linked (no chat_id)",
                kind_value,
                user.email,
            )
        else:
            ok = await self._telegram.send_message(
                user.telegram_chat_id, f"<b>{title}</b>\n{body}"
            )
            if ok:
                delivered.append("telegram")

        logger.info(
            "notify kind=%s user=%s delivered=%s",
            kind_value,
            user.email,
            ",".join(delivered) or "none",
        )

    async def emit_billing_reminder(
        self,
        user: User,
        host: Host,
        *,
        days_until: int,
        settings: UserNotificationSettings,
    ) -> None:
        if not host.billing_renewal_at:
            return

        due = host.billing_renewal_at.isoformat()
        when = (
            "today"
            if days_until == 0
            else f"in {days_until} day{'s' if days_until != 1 else ''}"
        )
        amount = ""
        if host.billing_amount is not None and host.billing_currency:
            amount = f" ({host.billing_amount} {host.billing_currency})"
        body = f"Host «{host.name}» renews {when} on {due}{amount}."

        await self.emit_activity(
            user,
            kind=NotificationKind.BILLING_REMINDER,
            title=f"Renewal: {host.name}",
            body=body,
            host_id=host.id,
            dedupe_key=f"{due}:{days_until}",
            payload={"days_until": days_until, "renewal_at": due},
            settings=settings,
        )

    async def emit_auto_renewed(self, user: User, host: Host) -> None:
        settings = await self._settings.get_or_create(user.id)
        due = host.billing_renewal_at.isoformat() if host.billing_renewal_at else "?"
        await self.emit_activity(
            user,
            kind=NotificationKind.BILLING_AUTO_RENEWED,
            title=f"Auto-renewed: {host.name}",
            body=f"Host «{host.name}» was advanced to the next period (next due {due}).",
            host_id=host.id,
            dedupe_key=f"auto:{due}",
            payload={"renewal_at": due},
            settings=settings,
        )

    async def _create_inbox(
        self,
        *,
        user_id: UUID,
        host_id: UUID | None,
        kind: str,
        title: str,
        body: str,
        dedupe_key: str,
        payload: dict | None = None,
    ) -> Notification | None:
        row = Notification(
            user_id=user_id,
            host_id=host_id,
            kind=kind,
            title=title,
            body=body,
            dedupe_key=dedupe_key,
            payload=payload,
        )
        try:
            async with self._session.begin_nested():
                self._session.add(row)
                await self._session.flush()
            await self._session.commit()
            return row
        except IntegrityError:
            return None


async def notify_user(
    session: AsyncSession,
    user: User | UUID,
    *,
    kind: NotificationKind | str,
    title: str,
    body: str,
    host_id: UUID | None = None,
) -> None:
    """Best-effort activity notify — never raises into the caller."""
    try:
        if isinstance(user, UUID):
            resolved = await UserRepository(session).get_by_id(user)
            if resolved is None:
                return
            user = resolved
        await NotificationService(session).emit_activity(
            user,
            kind=kind,
            title=title,
            body=body,
            host_id=host_id,
        )
    except Exception:
        logger.exception("notify_user failed kind=%s", kind)


async def process_daily_billing(session: AsyncSession) -> None:
    """Reminders + auto-renew for all billing-enabled hosts."""
    from app.repositories.host import HostRepository
    from app.services.billing import BillingService
    from app.websocket.manager import connection_manager

    hosts_repo = HostRepository(session)
    users_repo = UserRepository(session)
    notify = NotificationService(session)
    billing = BillingService(session)
    settings_repo = NotificationSettingsRepository(session)

    today = date.today()
    hosts = await hosts_repo.list_billing_enabled()
    for host in hosts:
        user = await users_repo.get_by_id(host.user_id)
        if user is None or not user.is_active:
            continue
        settings = await settings_repo.get_or_create(user.id)

        # Auto-renew when overdue and agent online
        if (
            host.billing_auto_renew
            and host.billing_renewal_at is not None
            and host.billing_renewal_at <= today
            and host.agent is not None
            and host.agent.is_online
            and await connection_manager.is_agent_online(host.agent.id)
        ):
            advanced = await billing.auto_advance_if_due(host)
            if advanced:
                refreshed = await hosts_repo.get_by_id_any(host.id)
                if refreshed:
                    await notify.emit_auto_renewed(user, refreshed)
            continue

        if not host.billing_renewal_at:
            continue
        days_until = (host.billing_renewal_at - today).days
        offsets = settings.reminder_offsets_days or [7, 3, 1, 0]
        if days_until in {int(o) for o in offsets}:
            await notify.emit_billing_reminder(
                user, host, days_until=days_until, settings=settings
            )
