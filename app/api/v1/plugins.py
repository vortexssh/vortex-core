from datetime import date
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession, RedisClient
from app.schemas.plugin import (
    PluginDailyMetricsList,
    PluginDailyMetricsUpsert,
    PluginDaemonBindingRead,
    PluginDaemonStatePush,
    PluginHostBindingRead,
    PluginHostBindingUpsert,
    PluginInstallCreate,
    PluginInstallCreated,
    PluginInstallRead,
    PluginInstallUpdate,
    PluginManifest,
    PluginRpcRequest,
    PluginRpcResponse,
    PluginStateRead,
    PluginUiBundle,
)
from app.services.plugin import PluginService
from app.services.plugin_state import PluginStateService

router = APIRouter(prefix="/plugins", tags=["plugins"])


def _require_daemon_token(token: str | None) -> str:
    if not token or not token.startswith("vxp_"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "invalid_daemon_token",
                "message": "X-Plugin-Token required",
            },
        )
    return token


@router.get("", response_model=list[PluginInstallRead])
async def list_plugins(user: CurrentUser, session: DbSession) -> list[PluginInstallRead]:
    return await PluginService(session).list_installs(user.id)


@router.get("/ui-bundle", response_model=PluginUiBundle)
async def get_ui_bundle(user: CurrentUser, session: DbSession) -> PluginUiBundle:
    return await PluginService(session).ui_bundle(user.id)


@router.post("", response_model=PluginInstallCreated, status_code=status.HTTP_201_CREATED)
async def install_plugin(
    payload: PluginInstallCreate,
    user: CurrentUser,
    session: DbSession,
) -> PluginInstallCreated:
    return await PluginService(session).install(user.id, payload)


@router.get("/{install_id}", response_model=PluginInstallRead)
async def get_plugin(
    install_id: UUID,
    user: CurrentUser,
    session: DbSession,
) -> PluginInstallRead:
    return await PluginService(session).get_install(user.id, install_id)


@router.patch("/{install_id}", response_model=PluginInstallRead)
async def update_plugin(
    install_id: UUID,
    payload: PluginInstallUpdate,
    user: CurrentUser,
    session: DbSession,
) -> PluginInstallRead:
    return await PluginService(session).update_install(user.id, install_id, payload)


@router.delete("/{install_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plugin(
    install_id: UUID,
    user: CurrentUser,
    session: DbSession,
) -> None:
    await PluginService(session).delete_install(user.id, install_id)


@router.post(
    "/{install_id}/rotate-token",
    response_model=PluginInstallCreated,
)
async def rotate_daemon_token(
    install_id: UUID,
    user: CurrentUser,
    session: DbSession,
) -> PluginInstallCreated:
    return await PluginService(session).rotate_daemon_token(user.id, install_id)


@router.get("/{install_id}/manifest", response_model=PluginManifest)
async def get_manifest(
    install_id: UUID,
    user: CurrentUser,
    session: DbSession,
) -> PluginManifest:
    return await PluginService(session).get_manifest(user.id, install_id)


@router.put(
    "/{install_id}/bindings/{host_id}",
    response_model=PluginHostBindingRead,
)
async def upsert_binding(
    install_id: UUID,
    host_id: UUID,
    payload: PluginHostBindingUpsert,
    user: CurrentUser,
    session: DbSession,
) -> PluginHostBindingRead:
    return await PluginService(session).upsert_binding(
        user.id, install_id, host_id, payload
    )


@router.delete(
    "/{install_id}/bindings/{host_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_binding(
    install_id: UUID,
    host_id: UUID,
    user: CurrentUser,
    session: DbSession,
) -> None:
    await PluginService(session).delete_binding(user.id, install_id, host_id)


@router.get("/{install_id}/state", response_model=PluginStateRead)
async def get_state(
    install_id: UUID,
    user: CurrentUser,
    session: DbSession,
    redis: RedisClient,
    host_id: UUID | None = Query(default=None),
) -> PluginStateRead:
    return await PluginService(session).get_state(
        user.id,
        install_id,
        PluginStateService(redis),
        host_id=host_id,
    )


@router.post("/{install_id}/rpc/{method}", response_model=PluginRpcResponse)
async def call_rpc(
    install_id: UUID,
    method: str,
    payload: PluginRpcRequest,
    user: CurrentUser,
    session: DbSession,
) -> PluginRpcResponse:
    return await PluginService(session).rpc(user.id, install_id, method, payload)


@router.get("/{install_id}/metrics/daily", response_model=PluginDailyMetricsList)
async def list_daily_metrics(
    install_id: UUID,
    user: CurrentUser,
    session: DbSession,
    metric: str = Query(default="energy_kwh", min_length=1, max_length=64),
    host_id: UUID | None = Query(default=None),
    from_day: date = Query(alias="from"),
    to_day: date = Query(alias="to"),
) -> PluginDailyMetricsList:
    return await PluginService(session).list_daily_metrics(
        user.id,
        install_id,
        metric=metric,
        day_from=from_day,
        day_to=to_day,
        host_id=host_id,
    )


@router.post(
    "/{install_id}/daemon/state",
    response_model=PluginStateRead,
)
async def daemon_push_state(
    install_id: UUID,
    payload: PluginDaemonStatePush,
    session: DbSession,
    redis: RedisClient,
    x_plugin_token: str | None = Header(default=None, alias="X-Plugin-Token"),
) -> PluginStateRead:
    token = _require_daemon_token(x_plugin_token)
    service = PluginService(session)
    install = await service.authenticate_daemon(install_id, token)
    return await service.daemon_push_state(
        install, payload, PluginStateService(redis)
    )


@router.get(
    "/{install_id}/daemon/bindings",
    response_model=list[PluginDaemonBindingRead],
)
async def daemon_list_bindings(
    install_id: UUID,
    session: DbSession,
    x_plugin_token: str | None = Header(default=None, alias="X-Plugin-Token"),
) -> list[PluginDaemonBindingRead]:
    token = _require_daemon_token(x_plugin_token)
    service = PluginService(session)
    install = await service.authenticate_daemon(install_id, token)
    return await service.daemon_list_bindings(install)


@router.post(
    "/{install_id}/daemon/metrics/daily",
    response_model=PluginDailyMetricsList,
)
async def daemon_upsert_daily_metrics(
    install_id: UUID,
    payload: PluginDailyMetricsUpsert,
    session: DbSession,
    x_plugin_token: str | None = Header(default=None, alias="X-Plugin-Token"),
) -> PluginDailyMetricsList:
    token = _require_daemon_token(x_plugin_token)
    service = PluginService(session)
    install = await service.authenticate_daemon(install_id, token)
    return await service.daemon_upsert_daily_metrics(install, payload)
