from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tag import Tag


class TagRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user(self, user_id: UUID) -> list[Tag]:
        result = await self._session.execute(
            select(Tag).where(Tag.user_id == user_id).order_by(Tag.name)
        )
        return list(result.scalars().all())

    async def get_by_id(self, tag_id: UUID, user_id: UUID) -> Tag | None:
        result = await self._session.execute(
            select(Tag).where(Tag.id == tag_id, Tag.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def create(self, tag: Tag) -> Tag:
        self._session.add(tag)
        await self._session.flush()
        await self._session.refresh(tag)
        return tag

    async def save(self, tag: Tag) -> Tag:
        self._session.add(tag)
        await self._session.flush()
        await self._session.refresh(tag)
        return tag

    async def delete(self, tag: Tag) -> None:
        await self._session.delete(tag)
        await self._session.flush()
