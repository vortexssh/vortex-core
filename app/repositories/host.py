from uuid import UUID

from sqlalchemy import select
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
        query = query.order_by(Host.created_at.desc()).offset(offset).limit(limit)
        result = await self._session.execute(query)
        return list(result.scalars().unique().all())

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
        if tag not in host.tags:
            host.tags.append(tag)
        return await self.save(host)

    async def detach_tag(self, host: Host, tag: Tag) -> Host:
        if tag in host.tags:
            host.tags.remove(tag)
        return await self.save(host)
