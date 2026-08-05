from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession, RedisClient, UserWith2FA
from app.schemas.host import (
    HostCreate,
    HostHiddenToggle,
    HostProxyToggle,
    HostRead,
    HostReorder,
    HostTagsUpdate,
    HostUpdate,
)
from app.schemas.task import TelemetryRead
from app.services.host import HostService
from app.services.telemetry import TelemetryService

router = APIRouter(prefix="/hosts", tags=["hosts"])


@router.get("", response_model=list[HostRead])
async def list_hosts(
    user: CurrentUser,
    session: DbSession,
    redis: RedisClient,
    tag_id: UUID | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> list[HostRead]:
    service = HostService(session)
    hosts = await service.list_hosts(
        user.id, tag_id=tag_id, offset=offset, limit=limit, redis=redis
    )
    return [HostRead.model_validate(h) for h in hosts]


@router.post("", response_model=HostRead, status_code=status.HTTP_201_CREATED)
async def create_host(
    payload: HostCreate,
    user: CurrentUser,
    session: DbSession,
    redis: RedisClient,
) -> HostRead:
    service = HostService(session)
    host = await service.create_host(user.id, payload, redis)
    return HostRead.model_validate(host)


@router.patch("/reorder", response_model=list[HostRead])
async def reorder_hosts(
    payload: HostReorder,
    user: CurrentUser,
    session: DbSession,
) -> list[HostRead]:
    service = HostService(session)
    hosts = await service.reorder_hosts(user.id, payload.host_ids)
    return [HostRead.model_validate(h) for h in hosts]


@router.get("/{host_id}", response_model=HostRead)
async def get_host(
    host_id: UUID,
    user: CurrentUser,
    session: DbSession,
    redis: RedisClient,
) -> HostRead:
    service = HostService(session)
    host = await service.get_host(user.id, host_id, redis)
    return HostRead.model_validate(host)


@router.patch("/{host_id}", response_model=HostRead)
async def update_host(
    host_id: UUID,
    payload: HostUpdate,
    user: CurrentUser,
    session: DbSession,
    redis: RedisClient,
) -> HostRead:
    service = HostService(session)
    host = await service.update_host(user.id, host_id, payload, redis)
    return HostRead.model_validate(host)


@router.patch("/{host_id}/proxy", response_model=HostRead)
async def toggle_proxy(
    host_id: UUID,
    payload: HostProxyToggle,
    user: CurrentUser,
    session: DbSession,
) -> HostRead:
    service = HostService(session)
    host = await service.set_proxy(user.id, host_id, payload.is_proxy_enabled)
    return HostRead.model_validate(host)


@router.patch("/{host_id}/hidden", response_model=HostRead)
async def toggle_hidden(
    host_id: UUID,
    payload: HostHiddenToggle,
    user: CurrentUser,
    session: DbSession,
) -> HostRead:
    service = HostService(session)
    host = await service.set_hidden(user.id, host_id, payload.is_hidden)
    return HostRead.model_validate(host)


@router.delete("/{host_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_host(
    host_id: UUID,
    user: CurrentUser,
    session: DbSession,
) -> None:
    service = HostService(session)
    await service.delete_host(user.id, host_id)


@router.put("/{host_id}/tags", response_model=HostRead)
async def set_host_tags(
    host_id: UUID,
    payload: HostTagsUpdate,
    user: CurrentUser,
    session: DbSession,
) -> HostRead:
    service = HostService(session)
    host = await service.set_host_tags(user.id, host_id, payload.tag_ids)
    return HostRead.model_validate(host)


@router.post("/{host_id}/tags/{tag_id}", response_model=HostRead)
async def attach_tag(
    host_id: UUID,
    tag_id: UUID,
    user: CurrentUser,
    session: DbSession,
) -> HostRead:
    service = HostService(session)
    host = await service.attach_tag(user.id, host_id, tag_id)
    return HostRead.model_validate(host)


@router.delete("/{host_id}/tags/{tag_id}", response_model=HostRead)
async def detach_tag(
    host_id: UUID,
    tag_id: UUID,
    user: CurrentUser,
    session: DbSession,
) -> HostRead:
    service = HostService(session)
    host = await service.detach_tag(user.id, host_id, tag_id)
    return HostRead.model_validate(host)


@router.get("/{host_id}/telemetry", response_model=TelemetryRead)
async def get_telemetry(
    host_id: UUID,
    user: UserWith2FA,
    session: DbSession,
    redis: RedisClient,
) -> TelemetryRead:
    host_service = HostService(session)
    await host_service.get_host(user.id, host_id)
    telemetry = TelemetryService(redis)
    data = await telemetry.get(host_id)
    if data is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "telemetry_missing", "message": "No telemetry available"},
        )
    return data


@router.get("/{host_id}/telemetry/history", response_model=list[TelemetryRead])
async def get_telemetry_history(
    host_id: UUID,
    user: UserWith2FA,
    session: DbSession,
    redis: RedisClient,
) -> list[TelemetryRead]:
    host_service = HostService(session)
    await host_service.get_host(user.id, host_id)
    return await TelemetryService(redis).history(host_id)
