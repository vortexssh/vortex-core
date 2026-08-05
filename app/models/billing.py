"""Billing / notification enums and shared helpers."""

from __future__ import annotations

from datetime import date, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.host import Host


class BillingCycle(StrEnum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    SEMIANNUAL = "semiannual"
    ANNUAL = "annual"
    CUSTOM = "custom"


class NotificationKind(StrEnum):
    BILLING_REMINDER = "billing_reminder"
    BILLING_AUTO_RENEWED = "billing_auto_renewed"
    LOGIN = "login"
    PASSWORD_CHANGED = "password_changed"
    TWOFA_ENABLED = "2fa_enabled"
    TWOFA_DISABLED = "2fa_disabled"
    PROFILE_UPDATED = "profile_updated"
    TELEGRAM_LINKED = "telegram_linked"
    TELEGRAM_UNLINKED = "telegram_unlinked"
    HOST_CREATED = "host_created"
    HOST_UPDATED = "host_updated"
    HOST_DELETED = "host_deleted"
    AGENT_CREATED = "agent_created"
    AGENT_ROTATED = "agent_rotated"
    AGENT_REVOKED = "agent_revoked"
    API_KEY_CREATED = "api_key_created"
    API_KEY_DELETED = "api_key_deleted"
    TASK_CREATED = "task_created"
    TASK_UPDATED = "task_updated"
    TASK_DELETED = "task_deleted"
    BILLING_ADVANCED = "billing_advanced"


# Maps kind → UserNotificationSettings boolean column
KIND_SETTING_ATTR: dict[str, str] = {
    NotificationKind.BILLING_REMINDER: "billing_reminders_enabled",
    NotificationKind.BILLING_AUTO_RENEWED: "notify_billing_auto_renewed",
    NotificationKind.LOGIN: "notify_login",
    NotificationKind.PASSWORD_CHANGED: "notify_password_changed",
    NotificationKind.TWOFA_ENABLED: "notify_2fa_enabled",
    NotificationKind.TWOFA_DISABLED: "notify_2fa_disabled",
    NotificationKind.PROFILE_UPDATED: "notify_profile_updated",
    NotificationKind.TELEGRAM_LINKED: "notify_telegram_linked",
    NotificationKind.TELEGRAM_UNLINKED: "notify_telegram_unlinked",
    NotificationKind.HOST_CREATED: "notify_host_created",
    NotificationKind.HOST_UPDATED: "notify_host_updated",
    NotificationKind.HOST_DELETED: "notify_host_deleted",
    NotificationKind.AGENT_CREATED: "notify_agent_created",
    NotificationKind.AGENT_ROTATED: "notify_agent_rotated",
    NotificationKind.AGENT_REVOKED: "notify_agent_revoked",
    NotificationKind.API_KEY_CREATED: "notify_api_key_created",
    NotificationKind.API_KEY_DELETED: "notify_api_key_deleted",
    NotificationKind.TASK_CREATED: "notify_task_created",
    NotificationKind.TASK_UPDATED: "notify_task_updated",
    NotificationKind.TASK_DELETED: "notify_task_deleted",
    NotificationKind.BILLING_ADVANCED: "notify_billing_advanced",
}


def add_billing_period(
    start: date,
    cycle: BillingCycle | str,
    custom_days: int | None = None,
) -> date:
    """Advance a renewal date by one billing period."""
    cycle_value = BillingCycle(cycle) if not isinstance(cycle, BillingCycle) else cycle
    if cycle_value == BillingCycle.MONTHLY:
        return _add_months(start, 1)
    if cycle_value == BillingCycle.QUARTERLY:
        return _add_months(start, 3)
    if cycle_value == BillingCycle.SEMIANNUAL:
        return _add_months(start, 6)
    if cycle_value == BillingCycle.ANNUAL:
        return _add_months(start, 12)
    days = custom_days if custom_days and custom_days > 0 else 30
    return start + timedelta(days=days)


def _add_months(start: date, months: int) -> date:
    month = start.month - 1 + months
    year = start.year + month // 12
    month = month % 12 + 1
    # Clamp day to last day of target month
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    last_day = (next_month - timedelta(days=1)).day
    day = min(start.day, last_day)
    return date(year, month, day)


def host_billing_ready(host: Host) -> bool:
    return bool(
        host.billing_enabled
        and host.billing_renewal_at is not None
        and host.billing_cycle is not None
    )
