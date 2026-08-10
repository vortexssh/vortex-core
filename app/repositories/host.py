from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.host import Host
from app.models.tag import Tag, host_tags


class HostRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _base_query(self):
        return select(Host).options(
            selectinload(Host.tags),
            selectinload(Host.agent),
            selectinload(Host.billing_payer),
        )

    async def get_by_id(self, host_id: UUID, user_id: UUID) -> Host | None:
        result = await self._session.execute(
            self._base_query().where(Host.id == host_id, Host.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_any(self, host_id: UUID) -> Host | None:
        result = await self._session.execute(
            self._base_query().where(Host.id == host_id)
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: UUID,
        *,
        tag_id: UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[Host]:
        query = self._base_query().where(Host.user_id == user_id)
        if tag_id is not None:
            query = query.join(host_tags).where(host_tags.c.tag_id == tag_id)
        query = query.order_by(Host.sort_order.asc(), Host.created_at.desc()).offset(offset).limit(limit)
        result = await self._session.execute(query)
        return list(result.scalars().unique().all())

    async def list_public_for_user(self, user_id: UUID) -> list[Host]:
        """Hosts visible on the public status page (not hidden)."""
        result = await self._session.execute(
            self._base_query()
            .where(Host.user_id == user_id, Host.is_hidden.is_(False))
            .order_by(Host.sort_order.asc(), Host.name.asc())
        )
        return list(result.scalars().unique().all())

    async def next_sort_order(self, user_id: UUID) -> int:
        result = await self._session.execute(
            select(func.coalesce(func.max(Host.sort_order), -1)).where(Host.user_id == user_id)
        )
        return int(result.scalar_one()) + 1

    async def create(self, host: Host) -> Host:
        self._session.add(host)
        await self._session.flush()
        await self._session.refresh(host, attribute_names=["tags", "agent"])
        return host

    async def save(self, host: Host) -> Host:
        self._session.add(host)
        await self._session.flush()
        await self._session.refresh(host, attribute_names=["tags", "agent"])
        return host

    async def delete(self, host: Host) -> None:
        await self._session.delete(host)
        await self._session.flush()

    async def attach_tag(self, host: Host, tag: Tag) -> Host:
        if not any(t.id == tag.id for t in host.tags):
            host.tags.append(tag)
        return await self.save(host)

    async def detach_tag(self, host: Host, tag: Tag) -> Host:
        host.tags = [t for t in host.tags if t.id != tag.id]
        return await self.save(host)

    async def set_tags(self, host: Host, tags: list[Tag]) -> Host:
        host.tags = list(tags)
        return await self.save(host)

    async def list_billing_enabled(self) -> list[Host]:
        result = await self._session.execute(
            self._base_query().where(Host.billing_enabled.is_(True))
        )
        return list(result.scalars().unique().all())

    async def list_billing_for_user(
        self,
        user_id: UUID,
        *,
        payer_id: UUID | None = None,
    ) -> list[Host]:
        query = self._base_query().where(
            Host.user_id == user_id,
            Host.billing_enabled.is_(True),
        )
        if payer_id is not None:
            query = query.where(Host.billing_payer_id == payer_id)
        result = await self._session.execute(query)
        return list(result.scalars().unique().all())

    async def list_for_payer(self, user_id: UUID, payer_id: UUID) -> list[Host]:
        result = await self._session.execute(
            self._base_query().where(
                Host.user_id == user_id,
                Host.billing_payer_id == payer_id,
            )
        )
        return list(result.scalars().unique().all())

    async def list_renewals_in_month(
        self,
        user_id: UUID,
        *,
        year: int,
        month: int,
    ) -> list[Host]:
        from calendar import monthrange
        from datetime import date

        start = date(year, month, 1)
        end = date(year, month, monthrange(year, month)[1])
        result = await self._session.execute(
            self._base_query().where(
                Host.user_id == user_id,
                Host.billing_enabled.is_(True),
                Host.billing_renewal_at.is_not(None),
                Host.billing_renewal_at >= start,
                Host.billing_renewal_at <= end,
            )
        )
        return list(result.scalars().unique().all())
