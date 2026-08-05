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
