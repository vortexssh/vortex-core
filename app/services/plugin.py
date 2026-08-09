from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_plugin_token, hash_secret, verify_secret
from app.models.plugin import PluginHostBinding, PluginInstall
from app.repositories.host import HostRepository
from app.repositories.plugin import PluginRepository
from app.repositories.plugin_metrics import PluginMetricsRepository
from app.schemas.plugin import (
    PluginDailyMetricRead,
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
from app.services.plugin_manifest import (
    assert_rpc_method,
    build_ui_contributions,
    parse_manifest,
    validate_against_schema,
)
from app.services.plugin_state import PluginStateService
from app.websocket.plugin_manager import plugin_connection_manager


class PluginService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = PluginRepository(session)
        self._hosts = HostRepository(session)
        self._metrics = PluginMetricsRepository(session)

    async def list_installs(self, user_id: UUID) -> list[PluginInstallRead]:
        rows = await self._repo.list_for_user(user_id)
        return [self._to_read(r) for r in rows]

    async def get_install(self, user_id: UUID, install_id: UUID) -> PluginInstallRead:
        row = await self._require_install(user_id, install_id)
        return self._to_read(row)

    async def install(
        self,
        user_id: UUID,
        payload: PluginInstallCreate,
    ) -> PluginInstallCreated:
        manifest = parse_manifest(payload.manifest)
        existing = await self._repo.get_by_plugin_id(user_id, manifest.id)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "plugin_already_installed",
                    "message": f"Plugin already installed: {manifest.id}",
                },
            )
        config = validate_against_schema(
            payload.config,
            manifest.config_schema,
            schemas=manifest.schemas,
            field_name="config",
        )
        raw_token = generate_plugin_token()
        install = PluginInstall(
            user_id=user_id,
            plugin_id=manifest.id,
            name=manifest.name,
            version=manifest.version,
            status="active",
            config=config,
            manifest=manifest.model_dump(mode="json"),
            daemon_token_hash=hash_secret(raw_token),
            daemon_token_prefix=raw_token[:12],
        )
        install = await self._repo.create(install)
        await self._session.commit()
        install = await self._repo.get_by_id(install.id, user_id)
        assert install is not None
        read = self._to_read(install)
        return PluginInstallCreated(**read.model_dump(), daemon_token=raw_token)

    async def update_install(
        self,
        user_id: UUID,
        install_id: UUID,
        payload: PluginInstallUpdate,
    ) -> PluginInstallRead:
        install = await self._require_install(user_id, install_id)
        manifest = parse_manifest(
            payload.manifest if payload.manifest is not None else install.manifest
        )
        if payload.manifest is not None:
            install.manifest = manifest.model_dump(mode="json")
            install.plugin_id = manifest.id
            install.name = manifest.name
            install.version = manifest.version
        if payload.status is not None:
            install.status = payload.status
        if payload.config is not None:
            install.config = validate_against_schema(
                payload.config,
                manifest.config_schema,
                schemas=manifest.schemas,
                field_name="config",
            )
        await self._repo.save(install)
        await self._session.commit()
        install = await self._require_install(user_id, install_id)
        return self._to_read(install)

    async def delete_install(self, user_id: UUID, install_id: UUID) -> None:
        install = await self._require_install(user_id, install_id)
        await self._repo.delete(install)
        await self._session.commit()

    async def rotate_daemon_token(
        self,
        user_id: UUID,
        install_id: UUID,
    ) -> PluginInstallCreated:
        install = await self._require_install(user_id, install_id)
        raw_token = generate_plugin_token()
        install.daemon_token_hash = hash_secret(raw_token)
        install.daemon_token_prefix = raw_token[:12]
        await self._repo.save(install)
        await self._session.commit()
        install = await self._require_install(user_id, install_id)
        read = self._to_read(install)
        return PluginInstallCreated(**read.model_dump(), daemon_token=raw_token)

    async def upsert_binding(
        self,
        user_id: UUID,
        install_id: UUID,
        host_id: UUID,
        payload: PluginHostBindingUpsert,
    ) -> PluginHostBindingRead:
        install = await self._require_install(user_id, install_id)
        manifest = parse_manifest(install.manifest)
        if "host.bind" not in manifest.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "permission_denied",
                    "message": "Plugin does not have host.bind permission",
                },
            )
        host = await self._hosts.get_by_id(host_id, user_id)
        if host is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "host_not_found", "message": "Host not found"},
            )
        config = validate_against_schema(
            payload.config,
            manifest.host_binding_schema,
            schemas=manifest.schemas,
            field_name="binding.config",
        )
        binding = await self._repo.get_binding(install_id, host_id)
        if binding is None:
            binding = PluginHostBinding(
                install_id=install_id,
                host_id=host_id,
                config=config,
            )
        else:
            binding.config = config
        binding = await self._repo.upsert_binding(binding)
        await self._session.commit()
        return PluginHostBindingRead.model_validate(binding)

    async def delete_binding(
        self,
        user_id: UUID,
        install_id: UUID,
        host_id: UUID,
    ) -> None:
        await self._require_install(user_id, install_id)
        binding = await self._repo.get_binding(install_id, host_id)
        if binding is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "binding_not_found", "message": "Binding not found"},
            )
        await self._repo.delete_binding(binding)
        await self._session.commit()

    async def ui_bundle(self, user_id: UUID) -> PluginUiBundle:
        installs = await self._repo.list_active_for_user(user_id)
        return PluginUiBundle(
            installs=[self._to_read(i) for i in installs],
            contributions=build_ui_contributions(installs),
        )

    async def get_manifest(self, user_id: UUID, install_id: UUID) -> PluginManifest:
        install = await self._require_install(user_id, install_id)
        return parse_manifest(install.manifest)

    async def get_state(
        self,
        user_id: UUID,
        install_id: UUID,
        state_service: PluginStateService,
        *,
        host_id: UUID | None = None,
    ) -> PluginStateRead:
        await self._require_install(user_id, install_id)
        if host_id is not None:
            host = await self._hosts.get_by_id(host_id, user_id)
            if host is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": "host_not_found", "message": "Host not found"},
                )
        return await state_service.get(install_id, host_id=host_id)

    async def rpc(
        self,
        user_id: UUID,
        install_id: UUID,
        method: str,
        payload: PluginRpcRequest,
    ) -> PluginRpcResponse:
        install = await self._require_install(user_id, install_id)
        if install.status != "active":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "plugin_disabled", "message": "Plugin is disabled"},
            )
        manifest = parse_manifest(install.manifest)
        assert_rpc_method(manifest, method)
        if payload.host_id is not None:
            host = await self._hosts.get_by_id(payload.host_id, user_id)
            if host is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": "host_not_found", "message": "Host not found"},
                )
        try:
            result = await plugin_connection_manager.rpc(
                install_id,
                method,
                payload.params,
                host_id=payload.host_id,
            )
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "daemon_offline", "message": str(exc)},
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail={"code": "rpc_failed", "message": str(exc)},
            ) from exc
        return PluginRpcResponse(result=result)

    async def authenticate_daemon(
        self,
        install_id: UUID,
        token: str,
    ) -> PluginInstall:
        install = await self._repo.get_by_id(install_id)
        if install is None or install.status != "active":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "invalid_daemon_token", "message": "Invalid install"},
            )
        if not verify_secret(token, install.daemon_token_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "invalid_daemon_token", "message": "Invalid token"},
            )
        return install

    async def daemon_push_state(
        self,
        install: PluginInstall,
        payload: PluginDaemonStatePush,
        state_service: PluginStateService,
    ) -> PluginStateRead:
        manifest = parse_manifest(install.manifest)
        if "state.write" not in manifest.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "permission_denied",
                    "message": "Plugin does not have state.write permission",
                },
            )
        if payload.host_id is not None:
            binding = await self._repo.get_binding(install.id, payload.host_id)
            if binding is None:
                # Allow push without binding if host belongs to user
                host = await self._hosts.get_by_id(payload.host_id, install.user_id)
                if host is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={"code": "host_not_found", "message": "Host not found"},
                    )
        return await state_service.store(
            install.id,
            payload.state,
            host_id=payload.host_id,
            history_key=payload.history_key,
        )

    async def set_daemon_online(self, install_id: UUID, online: bool) -> None:
        install = await self._repo.get_by_id(install_id)
        if install is None:
            return
        install.is_daemon_online = online
        await self._repo.save(install)
        await self._session.commit()

    async def daemon_list_bindings(
        self,
        install: PluginInstall,
    ) -> list[PluginDaemonBindingRead]:
        rows = await self._repo.list_bindings(install.id)
        return [
            PluginDaemonBindingRead(host_id=b.host_id, config=b.config or {})
            for b in rows
        ]

    async def daemon_upsert_daily_metrics(
        self,
        install: PluginInstall,
        payload: PluginDailyMetricsUpsert,
    ) -> PluginDailyMetricsList:
        manifest = parse_manifest(install.manifest)
        if "state.write" not in manifest.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "permission_denied",
                    "message": "Plugin does not have state.write permission",
                },
            )
        out: list[PluginDailyMetricRead] = []
        for sample in payload.samples:
            if sample.host_id is not None:
                host = await self._hosts.get_by_id(sample.host_id, install.user_id)
                if host is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "code": "host_not_found",
                            "message": f"Host not found: {sample.host_id}",
                        },
                    )
            await self._metrics.upsert_sample(
                install_id=install.id,
                host_id=sample.host_id,
                metric=sample.metric,
                day=sample.day,
                value=sample.value,
                meta=sample.meta,
            )
            out.append(
                PluginDailyMetricRead(
                    install_id=install.id,
                    host_id=sample.host_id,
                    metric=sample.metric,
                    day=sample.day,
                    value=sample.value,
                    meta=sample.meta,
                )
            )
        await self._session.commit()
        return PluginDailyMetricsList(samples=out)

    async def list_daily_metrics(
        self,
        user_id: UUID,
        install_id: UUID,
        *,
        metric: str,
        day_from: date,
        day_to: date,
        host_id: UUID | None = None,
    ) -> PluginDailyMetricsList:
        await self._require_install(user_id, install_id)
        if host_id is not None:
            host = await self._hosts.get_by_id(host_id, user_id)
            if host is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": "host_not_found", "message": "Host not found"},
                )
        if day_to < day_from:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "invalid_range", "message": "`to` must be >= `from`"},
            )
        rows = await self._metrics.list_range(
            install_id=install_id,
            metric=metric,
            day_from=day_from,
            day_to=day_to,
            host_id=host_id,
        )
        return PluginDailyMetricsList(
            samples=[PluginDailyMetricRead.model_validate(r) for r in rows]
        )

    async def _require_install(
        self,
        user_id: UUID,
        install_id: UUID,
    ) -> PluginInstall:
        install = await self._repo.get_by_id(install_id, user_id)
        if install is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "plugin_not_found", "message": "Plugin install not found"},
            )
        return install

    def _to_read(self, install: PluginInstall) -> PluginInstallRead:
        return PluginInstallRead(
            id=install.id,
            plugin_id=install.plugin_id,
            name=install.name,
            version=install.version,
            status=install.status,
            is_daemon_online=install.is_daemon_online
            or plugin_connection_manager.is_online(install.id),
            config=install.config or {},
            manifest=install.manifest or {},
            host_bindings=[
                PluginHostBindingRead.model_validate(b)
                for b in (install.host_bindings or [])
            ],
            created_at=install.created_at,
            updated_at=install.updated_at,
        )
