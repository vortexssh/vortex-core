from calendar import monthrange
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession, RedisClient
from app.core.config import get_settings
from app.schemas.billing import (
    BillingCalendarResponse,
    BillingSummaryResponse,
    NotificationRead,
    NotificationSettingsRead,
    NotificationSettingsUpdate,
    TelegramConfirmRequest,
    TelegramLinkResponse,
    TelegramStatusRead,
)
from app.schemas.host import HostRead
from app.services.billing import BillingService
from app.services.notifications import NotificationService
from app.services.telegram import TelegramService

router = APIRouter(tags=["billing"])


def _require_bot_api_key(
    x_bot_api_key: str | None = Header(default=None, alias="X-Bot-Api-Key"),
) -> None:
    settings = get_settings()
    expected = settings.telegram_bot_api_key.strip()
    if not expected or not x_bot_api_key or x_bot_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_bot_key", "message": "Invalid bot API key"},
        )


@router.get("/billing/summary", response_model=BillingSummaryResponse)
async def billing_summary(
    user: CurrentUser,
    session: DbSession,
    redis: RedisClient,
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
) -> BillingSummaryResponse:
    return await BillingService(session, redis).summary(
        user.id, from_date=from_date, to_date=to_date
    )


@router.get("/billing/calendar", response_model=BillingCalendarResponse)
async def billing_calendar(
    user: CurrentUser,
    session: DbSession,
    redis: RedisClient,
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
) -> BillingCalendarResponse:
    # Validate month exists
    monthrange(year, month)
    return await BillingService(session, redis).calendar(user.id, year=year, month=month)


@router.post("/hosts/{host_id}/billing/advance", response_model=HostRead)
async def advance_host_billing(
    host_id: UUID,
    user: CurrentUser,
    session: DbSession,
) -> HostRead:
    host = await BillingService(session).advance_period(user.id, host_id)
    return HostRead.model_validate(host)


@router.get("/users/me/notification-settings", response_model=NotificationSettingsRead)
async def get_notification_settings(
    user: CurrentUser,
    session: DbSession,
) -> NotificationSettingsRead:
    settings = await NotificationService(session).get_settings(user.id)
    return NotificationSettingsRead.model_validate(settings)


@router.patch("/users/me/notification-settings", response_model=NotificationSettingsRead)
async def patch_notification_settings(
    payload: NotificationSettingsUpdate,
    user: CurrentUser,
    session: DbSession,
) -> NotificationSettingsRead:
    settings = await NotificationService(session).update_settings(user.id, payload)
    return NotificationSettingsRead.model_validate(settings)


@router.get("/users/me/telegram", response_model=TelegramStatusRead)
async def telegram_status(user: CurrentUser, session: DbSession) -> TelegramStatusRead:
    return await TelegramService(session).status_for(user)


@router.post("/users/me/telegram/link", response_model=TelegramLinkResponse)
async def telegram_link(user: CurrentUser, session: DbSession) -> TelegramLinkResponse:
    return await TelegramService(session).create_link_code(user.id)


@router.delete("/users/me/telegram", status_code=status.HTTP_204_NO_CONTENT)
async def telegram_unlink(user: CurrentUser, session: DbSession) -> None:
    await TelegramService(session).unlink(user.id)


@router.post(
    "/internal/telegram/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_require_bot_api_key)],
)
async def telegram_confirm(
    payload: TelegramConfirmRequest,
    session: DbSession,
) -> None:
    await TelegramService(session).confirm_link(code=payload.code, chat_id=payload.chat_id)


@router.get("/notifications", response_model=list[NotificationRead])
async def list_notifications(
    user: CurrentUser,
    session: DbSession,
    unread: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
) -> list[NotificationRead]:
    rows = await NotificationService(session).list_notifications(
        user.id, unread_only=unread, limit=limit
    )
    return [NotificationRead.model_validate(r) for r in rows]


@router.post("/notifications/{notification_id}/read", response_model=NotificationRead)
async def read_notification(
    notification_id: UUID,
    user: CurrentUser,
    session: DbSession,
) -> NotificationRead:
    row = await NotificationService(session).mark_read(user.id, notification_id)
    return NotificationRead.model_validate(row)


@router.post("/notifications/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def read_all_notifications(user: CurrentUser, session: DbSession) -> None:
    await NotificationService(session).mark_all_read(user.id)
