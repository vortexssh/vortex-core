"""Public status page — unauthenticated host telemetry / billing / energy."""

from calendar import monthrange
from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.host import HostRepository
from app.repositories.plugin_metrics import PluginMetricsRepository
from app.repositories.user import UserRepository
from app.schemas.public import (
    PublicBilling,
    PublicEnergy,
    PublicEnergyDay,
    PublicHost,
    PublicStatusPage,
    PublicTelemetry,
)
from app.services.host import HostService
from app.services.telemetry import TelemetryService


class PublicStatusService:
    def __init__(self, session: AsyncSession, redis: Redis) -> None:
        self._session = session
        self._redis = redis
        self._users = UserRepository(session)
        self._hosts = HostRepository(session)
        self._telemetry = TelemetryService(redis)
        self._metrics = PluginMetricsRepository(session)

    async def get_page(self, slug: str) -> PublicStatusPage:
        normalized = slug.strip().lower()
        user = await self._users.get_by_public_slug(normalized)
        if user is None or not user.is_active or user.public_slug is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "status_not_found", "message": "Status page not found"},
            )

        hosts = await self._hosts.list_public_for_user(user.id)
        await HostService(self._session).backfill_missing_geoip(hosts, self._redis)
        host_ids = [h.id for h in hosts]
        telemetry_list = await self._telemetry.get_many(host_ids)
        by_host: dict[UUID, PublicTelemetry] = {
            t.host_id: PublicTelemetry(
                cpu_percent=t.cpu_percent,
                ram_percent=t.ram_percent,
                net_bytes_sent=t.net_bytes_sent,
                net_bytes_recv=t.net_bytes_recv,
                uptime_seconds=t.uptime_seconds,
                collected_at=t.collected_at,
            )
            for t in telemetry_list
        }

        today = datetime.now(UTC).date()
        month_start = date(today.year, today.month, 1)
        month_end = date(
            today.year,
            today.month,
            monthrange(today.year, today.month)[1],
        )
        energy_rows = await self._metrics.list_for_user_hosts(
            user_id=user.id,
            host_ids=host_ids,
            metric="energy_kwh",
            day_from=month_start,
            day_to=month_end,
        )
        energy_by_host: dict[UUID, list[PublicEnergyDay]] = {}
        for row in energy_rows:
            if row.host_id is None:
                continue
            energy_by_host.setdefault(row.host_id, []).append(
                PublicEnergyDay(day=row.day, value=float(row.value))
            )

        public_hosts: list[PublicHost] = []
        for h in hosts:
            billing: PublicBilling | None = None
            if getattr(h, "billing_enabled", False):
                billing = PublicBilling(
                    enabled=True,
                    cycle=str(h.billing_cycle) if h.billing_cycle else None,
                    custom_days=h.billing_custom_days,
                    renewal_at=h.billing_renewal_at,
                    amount=float(h.billing_amount)
                    if h.billing_amount is not None
                    else None,
                    currency=h.billing_currency,
                    auto_renew=bool(h.billing_auto_renew),
                )

            calendar = energy_by_host.get(h.id, [])
            energy: PublicEnergy | None = None
            if calendar:
                today_val = next((d.value for d in calendar if d.day == today), None)
                month_sum = sum(d.value for d in calendar)
                energy = PublicEnergy(
                    metric="energy_kwh",
                    unit="kWh",
                    today_kwh=today_val,
                    month_kwh=round(month_sum, 3),
                    calendar=calendar,
                )

            public_hosts.append(
                PublicHost(
                    id=h.id,
                    name=h.name,
                    country_code=h.country_code,
                    agent_online=bool(h.agent and h.agent.is_online),
                    telemetry=by_host.get(h.id),
                    billing=billing,
                    energy=energy,
                )
            )
        return PublicStatusPage(slug=user.public_slug, hosts=public_hosts)
