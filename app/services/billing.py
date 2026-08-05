"""Host billing: advance periods, spend summary, calendar."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import add_billing_period, host_billing_ready
from app.models.host import Host
from app.repositories.host import HostRepository
from app.repositories.user import UserRepository
from app.schemas.billing import (
    BillingCalendarResponse,
    BillingDay,
    BillingHostBrief,
    BillingSummaryItem,
    BillingSummaryResponse,
)
from app.services.fx import FxService


class BillingService:
    def __init__(self, session: AsyncSession, redis: Redis | None = None) -> None:
        self._hosts = HostRepository(session)
        self._users = UserRepository(session)
        self._session = session
        self._fx = FxService(redis)

    async def advance_period(self, user_id: UUID, host_id: UUID) -> Host:
        host = await self._hosts.get_by_id(host_id, user_id)
        if host is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "host_not_found", "message": "Host not found"},
            )
        if not host_billing_ready(host):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "billing_not_configured",
                    "message": "Enable billing with cycle and renewal date first",
                },
            )
        assert host.billing_renewal_at is not None
        assert host.billing_cycle is not None
        host.billing_renewal_at = add_billing_period(
            host.billing_renewal_at,
            host.billing_cycle,
            host.billing_custom_days,
        )
        await self._hosts.save(host)
        await self._session.commit()
        refreshed = await self._hosts.get_by_id(host_id, user_id)
        assert refreshed is not None
        return refreshed

    async def auto_advance_if_due(self, host: Host) -> bool:
        """Advance one period if past due. Returns True if advanced."""
        if not host.billing_auto_renew or not host_billing_ready(host):
            return False
        assert host.billing_renewal_at is not None
        assert host.billing_cycle is not None
        today = date.today()
        if host.billing_renewal_at > today:
            return False
        # Catch up if multiple periods overdue
        while host.billing_renewal_at <= today:
            host.billing_renewal_at = add_billing_period(
                host.billing_renewal_at,
                host.billing_cycle,
                host.billing_custom_days,
            )
        await self._hosts.save(host)
        await self._session.commit()
        return True

    async def calendar(
        self,
        user_id: UUID,
        *,
        year: int,
        month: int,
    ) -> BillingCalendarResponse:
        user = await self._users.get_by_id(user_id)
        assert user is not None
        currency = user.preferred_currency
        hosts = await self._hosts.list_renewals_in_month(user_id, year=year, month=month)
        by_day: dict[date, list[BillingHostBrief]] = defaultdict(list)
        for host in hosts:
            if host.billing_renewal_at is None:
                continue
            converted = None
            if host.billing_amount is not None and host.billing_currency:
                converted = await self._fx.convert(
                    Decimal(host.billing_amount),
                    host.billing_currency,
                    currency,
                )
            by_day[host.billing_renewal_at].append(
                BillingHostBrief(
                    id=host.id,
                    name=host.name,
                    billing_amount=host.billing_amount,
                    billing_currency=host.billing_currency,
                    amount_converted=converted,
                    country_code=host.country_code,
                )
            )
        days = [
            BillingDay(date=d, hosts=items)
            for d, items in sorted(by_day.items(), key=lambda x: x[0])
        ]
        return BillingCalendarResponse(year=year, month=month, currency=currency, days=days)

    async def summary(
        self,
        user_id: UUID,
        *,
        from_date: date,
        to_date: date,
    ) -> BillingSummaryResponse:
        if to_date < from_date:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "invalid_range", "message": "to must be >= from"},
            )
        user = await self._users.get_by_id(user_id)
        assert user is not None
        currency = user.preferred_currency
        hosts = await self._hosts.list_billing_for_user(user_id)
        items: list[BillingSummaryItem] = []
        skipped: list[str] = []
        total = Decimal("0.00")

        for host in hosts:
            if not host.billing_amount or not host.billing_currency:
                continue
            # Attribute cost to the renewal date if it falls in range;
            # otherwise still include as recurring cost for the period window
            # when renewal is within range OR billing is active in range.
            renewal = host.billing_renewal_at
            if renewal is not None and not (from_date <= renewal <= to_date):
                # Include hosts whose renewal falls in range only for calendar-style;
                # for spend summary include all enabled hosts prorated? Plan says
                # period spend — count hosts with renewal in range OR all active
                # billing for the window. Use: renewal in range OR (enabled and
                # amount set) for the selected window as "expected spend".
                continue

            converted = await self._fx.convert(
                Decimal(host.billing_amount),
                host.billing_currency,
                currency,
            )
            if converted is None:
                skipped.append(f"{host.name}: no FX {host.billing_currency}→{currency}")
            else:
                total += converted
            items.append(
                BillingSummaryItem(
                    host_id=host.id,
                    host_name=host.name,
                    amount=Decimal(host.billing_amount),
                    currency=host.billing_currency,
                    amount_converted=converted,
                    renewal_at=renewal,
                    cycle=host.billing_cycle,
                )
            )

        return BillingSummaryResponse(
            currency=currency,
            from_date=from_date,
            to_date=to_date,
            total=total,
            items=items,
            skipped=skipped,
        )
