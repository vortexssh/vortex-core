from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.host import Host
from app.models.tag import Tag
from app.repositories.host import HostRepository
from app.repositories.tag import TagRepository
from app.schemas.host import HostCreate, HostUpdate, TagCreate, TagUpdate


class HostService:
    def __init__(self, session: AsyncSession) -> None:
        self._hosts = HostRepository(session)
        self._tags = TagRepository(session)
        self._session = session

    async def list_hosts(
        self,
        user_id: UUID,
        *,
        tag_id: UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[Host]:
        return await self._hosts.list_for_user(
            user_id, tag_id=tag_id, offset=offset, limit=limit
        )

    async def get_host(self, user_id: UUID, host_id: UUID) -> Host:
        host = await self._hosts.get_by_id(host_id, user_id)
        if host is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "host_not_found", "message": "Host not found"},
            )
        return host

    async def create_host(self, user_id: UUID, payload: HostCreate) -> Host:
        host = Host(
            user_id=user_id,
            name=payload.name,
            ip_address=payload.ip_address,
            port=payload.port,
            username=payload.username,
            notes=payload.notes,
            country_code=payload.country_code,
            is_hidden=payload.is_hidden,
            is_proxy_enabled=payload.is_proxy_enabled,
            sort_order=await self._hosts.next_sort_order(user_id),
        )
        host = await self._hosts.create(host)
        await self._session.commit()
        return await self.get_host(user_id, host.id)

    async def update_host(
        self,
        user_id: UUID,
        host_id: UUID,
        payload: HostUpdate,
    ) -> Host:
        host = await self.get_host(user_id, host_id)
        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(host, key, value)
        await self._hosts.save(host)
        await self._session.commit()
        return await self.get_host(user_id, host_id)

    async def set_proxy(
        self,
        user_id: UUID,
        host_id: UUID,
        enabled: bool,
    ) -> Host:
        host = await self.get_host(user_id, host_id)
        host.is_proxy_enabled = enabled
        await self._hosts.save(host)
        await self._session.commit()
        return await self.get_host(user_id, host_id)

    async def set_hidden(
        self,
        user_id: UUID,
        host_id: UUID,
        hidden: bool,
    ) -> Host:
        host = await self.get_host(user_id, host_id)
        host.is_hidden = hidden
        await self._hosts.save(host)
        await self._session.commit()
        return await self.get_host(user_id, host_id)

    async def reorder_hosts(self, user_id: UUID, host_ids: list[UUID]) -> list[Host]:
        """Assign sort_order 0..n-1 from the given sequence (must all belong to user)."""
        seen: set[UUID] = set()
        ordered: list[Host] = []
        for hid in host_ids:
            if hid in seen:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"code": "duplicate_host", "message": "Duplicate host id in reorder"},
                )
            seen.add(hid)
            host = await self._hosts.get_by_id(hid, user_id)
            if host is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": "host_not_found", "message": f"Host not found: {hid}"},
                )
            ordered.append(host)

        for index, host in enumerate(ordered):
            host.sort_order = index
            await self._hosts.save(host)
        await self._session.commit()
        return await self.list_hosts(user_id, limit=200)

    async def delete_host(self, user_id: UUID, host_id: UUID) -> None:
        host = await self.get_host(user_id, host_id)
        await self._hosts.delete(host)
        await self._session.commit()

    async def attach_tag(
        self,
        user_id: UUID,
        host_id: UUID,
        tag_id: UUID,
    ) -> Host:
        host = await self.get_host(user_id, host_id)
        tag = await self._tags.get_by_id(tag_id, user_id)
        if tag is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "tag_not_found", "message": "Tag not found"},
            )
        try:
            await self._hosts.attach_tag(host, tag)
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
        return await self.get_host(user_id, host_id)

    async def detach_tag(
        self,
        user_id: UUID,
        host_id: UUID,
        tag_id: UUID,
    ) -> Host:
        host = await self.get_host(user_id, host_id)
        tag = await self._tags.get_by_id(tag_id, user_id)
        if tag is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "tag_not_found", "message": "Tag not found"},
            )
        await self._hosts.detach_tag(host, tag)
        await self._session.commit()
        return await self.get_host(user_id, host_id)

    async def set_host_tags(
        self,
        user_id: UUID,
        host_id: UUID,
        tag_ids: list[UUID],
    ) -> Host:
        host = await self.get_host(user_id, host_id)
        unique_ids = list(dict.fromkeys(tag_ids))
        tags: list[Tag] = []
        for tid in unique_ids:
            tag = await self._tags.get_by_id(tid, user_id)
            if tag is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": "tag_not_found", "message": f"Tag not found: {tid}"},
                )
            tags.append(tag)
        await self._hosts.set_tags(host, tags)
        await self._session.commit()
        return await self.get_host(user_id, host_id)


class TagService:
    def __init__(self, session: AsyncSession) -> None:
        self._tags = TagRepository(session)
        self._session = session

    async def list_tags(self, user_id: UUID) -> list[Tag]:
        return await self._tags.list_for_user(user_id)

    async def create_tag(self, user_id: UUID, payload: TagCreate) -> Tag:
        tag = Tag(user_id=user_id, name=payload.name, color=payload.color)
        try:
            tag = await self._tags.create(tag)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "tag_exists", "message": "Tag name already exists"},
            ) from exc
        return tag

    async def update_tag(
        self,
        user_id: UUID,
        tag_id: UUID,
        payload: TagUpdate,
    ) -> Tag:
        tag = await self._tags.get_by_id(tag_id, user_id)
        if tag is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "tag_not_found", "message": "Tag not found"},
            )
        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(tag, key, value)
        try:
            await self._tags.save(tag)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "tag_exists", "message": "Tag name already exists"},
            ) from exc
        return tag

    async def delete_tag(self, user_id: UUID, tag_id: UUID) -> None:
        tag = await self._tags.get_by_id(tag_id, user_id)
        if tag is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "tag_not_found", "message": "Tag not found"},
            )
        await self._tags.delete(tag)
        await self._session.commit()
