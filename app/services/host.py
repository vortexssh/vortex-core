from uuid import UUID

from fastapi import HTTPException, status
from redis.asyncio import Redis
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
        redis: Redis | None = None,
    ) -> list[Host]:
        hosts = await self._hosts.list_for_user(
            user_id, tag_id=tag_id, offset=offset, limit=limit
        )
        await self.backfill_missing_geoip(hosts, redis)
        return hosts

    async def get_host(
        self,
        user_id: UUID,
        host_id: UUID,
        redis: Redis | None = None,
    ) -> Host:
        host = await self._hosts.get_by_id(host_id, user_id)
        if host is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "host_not_found", "message": "Host not found"},
            )
        if host.country_code is None and host.ip_address:
            await self.apply_geoip(host.id, str(host.ip_address), redis)
            refreshed = await self._hosts.get_by_id(host_id, user_id)
            return refreshed or host
        return host

    async def backfill_missing_geoip(
        self,
        hosts: list[Host],
        redis: Redis | None = None,
    ) -> None:
        """Fill country_code from stored public IP when missing (no agent required)."""
        for host in hosts:
            if host.country_code or not host.ip_address:
                continue
            await self.apply_geoip(host.id, str(host.ip_address), redis)
            refreshed = await self._hosts.get_by_id_any(host.id)
            if refreshed is not None and refreshed.country_code:
                host.country_code = refreshed.country_code

    async def create_host(
        self,
        user_id: UUID,
        payload: HostCreate,
        redis: Redis | None = None,
    ) -> Host:
        host = Host(
            user_id=user_id,
            name=payload.name,
            ip_address=payload.ip_address,
            port=payload.port,
            username=payload.username,
            notes=payload.notes,
            country_code=None,
            is_hidden=payload.is_hidden,
            is_proxy_enabled=payload.is_proxy_enabled,
            sort_order=await self._hosts.next_sort_order(user_id),
            billing_enabled=payload.billing_enabled,
            billing_cycle=payload.billing_cycle,
            billing_custom_days=payload.billing_custom_days,
            billing_renewal_at=payload.billing_renewal_at,
            billing_amount=payload.billing_amount,
            billing_currency=payload.billing_currency,
            billing_auto_renew=payload.billing_auto_renew
            if payload.billing_auto_renew is not None
            else True,
            billing_notes=payload.billing_notes,
        )
        host = await self._hosts.create(host)
        await self._session.commit()
        await self._sync_country_from_ip(host.id, host.ip_address, redis)
        from app.models.billing import NotificationKind
        from app.services.notifications import notify_user

        await notify_user(
            self._session,
            user_id,
            kind=NotificationKind.HOST_CREATED,
            title="Host added",
            body=f"Host «{host.name}» was added to your panel.",
            host_id=host.id,
        )
        return await self.get_host(user_id, host.id)

    async def update_host(
        self,
        user_id: UUID,
        host_id: UUID,
        payload: HostUpdate,
        redis: Redis | None = None,
    ) -> Host:
        host = await self.get_host(user_id, host_id)
        data = payload.model_dump(exclude_unset=True)
        # country_code is derived from ip_address — ignore client overrides
        data.pop("country_code", None)
        for key, value in data.items():
            setattr(host, key, value)
        await self._hosts.save(host)
        await self._session.commit()
        await self._sync_country_from_ip(host_id, host.ip_address, redis)
        from app.models.billing import NotificationKind
        from app.services.notifications import notify_user

        await notify_user(
            self._session,
            user_id,
            kind=NotificationKind.HOST_UPDATED,
            title="Host updated",
            body=f"Host «{host.name}» was updated.",
            host_id=host.id,
        )
        return await self.get_host(user_id, host_id)

    async def _sync_country_from_ip(
        self,
        host_id: UUID,
        ip: str | None,
        redis: Redis | None = None,
    ) -> None:
        """Set or clear country_code from the host's configured IP (no agent required)."""
        if not ip:
            host = await self._hosts.get_by_id_any(host_id)
            if host is not None and host.country_code is not None:
                host.country_code = None
                await self._hosts.save(host)
                await self._session.commit()
            return
        await self.apply_geoip(host_id, str(ip), redis)

    async def apply_geoip(
        self,
        host_id: UUID,
        ip: str | None,
        redis: Redis | None = None,
    ) -> bool:
        """Resolve country from IP and persist on host. Returns True if updated."""
        if not ip:
            return False
        from app.services.geoip import lookup_country_code

        code = await lookup_country_code(ip, redis)
        if not code:
            return False
        host = await self._hosts.get_by_id_any(host_id)
        if host is None or host.country_code == code:
            return False
        host.country_code = code
        await self._hosts.save(host)
        await self._session.commit()
        return True

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
        name = host.name
        await self._hosts.delete(host)
        await self._session.commit()
        from app.models.billing import NotificationKind
        from app.services.notifications import notify_user

        await notify_user(
            self._session,
            user_id,
            kind=NotificationKind.HOST_DELETED,
            title="Host deleted",
            body=f"Host «{name}» was removed from your panel.",
        )

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
