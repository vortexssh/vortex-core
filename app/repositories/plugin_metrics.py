from datetime import date
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plugin import PluginDailyMetric


class PluginMetricsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_sample(
        self,
        *,
        install_id: UUID,
        host_id: UUID | None,
        metric: str,
        day: date,
        value: float,
        meta: dict | None = None,
    ) -> None:
        stmt = insert(PluginDailyMetric).values(
            install_id=install_id,
            host_id=host_id,
            metric=metric,
            day=day,
            value=value,
            meta=meta or {},
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_plugin_daily_metrics_install_host_metric_day",
            set_={
                "value": stmt.excluded.value,
                "meta": stmt.excluded.meta,
            },
        )
        await self._session.execute(stmt)

    async def list_range(
        self,
        *,
        install_id: UUID,
        metric: str,
        day_from: date,
        day_to: date,
        host_id: UUID | None = None,
    ) -> list[PluginDailyMetric]:
        cond = [
            PluginDailyMetric.install_id == install_id,
            PluginDailyMetric.metric == metric,
            PluginDailyMetric.day >= day_from,
            PluginDailyMetric.day <= day_to,
        ]
        if host_id is not None:
            cond.append(PluginDailyMetric.host_id == host_id)
        result = await self._session.execute(
            select(PluginDailyMetric)
            .where(and_(*cond))
            .order_by(PluginDailyMetric.day.asc())
        )
        return list(result.scalars().all())

    async def list_for_user_hosts(
        self,
        *,
        user_id: UUID,
        host_ids: list[UUID],
        metric: str,
        day_from: date,
        day_to: date,
    ) -> list[PluginDailyMetric]:
        if not host_ids:
            return []
        from app.models.plugin import PluginInstall

        result = await self._session.execute(
            select(PluginDailyMetric)
            .join(PluginInstall, PluginDailyMetric.install_id == PluginInstall.id)
            .where(
                PluginInstall.user_id == user_id,
                PluginDailyMetric.host_id.in_(host_ids),
                PluginDailyMetric.metric == metric,
                PluginDailyMetric.day >= day_from,
                PluginDailyMetric.day <= day_to,
            )
            .order_by(PluginDailyMetric.day.asc())
        )
        return list(result.scalars().all())
