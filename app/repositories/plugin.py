from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.plugin import PluginHostBinding, PluginInstall


class PluginRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user(self, user_id: UUID) -> list[PluginInstall]:
        result = await self._session.execute(
            select(PluginInstall)
            .where(PluginInstall.user_id == user_id)
            .options(selectinload(PluginInstall.host_bindings))
            .order_by(PluginInstall.created_at.asc())
        )
        return list(result.scalars().all())

    async def list_active_for_user(self, user_id: UUID) -> list[PluginInstall]:
        result = await self._session.execute(
            select(PluginInstall)
            .where(
                PluginInstall.user_id == user_id,
                PluginInstall.status == "active",
            )
            .options(selectinload(PluginInstall.host_bindings))
            .order_by(PluginInstall.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_by_id(
        self,
        install_id: UUID,
        user_id: UUID | None = None,
    ) -> PluginInstall | None:
        stmt = (
            select(PluginInstall)
            .where(PluginInstall.id == install_id)
            .options(selectinload(PluginInstall.host_bindings))
        )
        if user_id is not None:
            stmt = stmt.where(PluginInstall.user_id == user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_plugin_id(
        self,
        user_id: UUID,
        plugin_id: str,
    ) -> PluginInstall | None:
        result = await self._session.execute(
            select(PluginInstall)
            .where(
                PluginInstall.user_id == user_id,
                PluginInstall.plugin_id == plugin_id,
            )
            .options(selectinload(PluginInstall.host_bindings))
        )
        return result.scalar_one_or_none()

    async def find_by_token_prefix(self, prefix: str) -> list[PluginInstall]:
        result = await self._session.execute(
            select(PluginInstall).where(PluginInstall.daemon_token_prefix == prefix)
        )
        return list(result.scalars().all())

    async def create(self, install: PluginInstall) -> PluginInstall:
        self._session.add(install)
        await self._session.flush()
        await self._session.refresh(install)
        return install

    async def save(self, install: PluginInstall) -> PluginInstall:
        self._session.add(install)
        await self._session.flush()
        await self._session.refresh(install)
        return install

    async def delete(self, install: PluginInstall) -> None:
        await self._session.delete(install)

    async def get_binding(
        self,
        install_id: UUID,
        host_id: UUID,
    ) -> PluginHostBinding | None:
        result = await self._session.execute(
            select(PluginHostBinding).where(
                PluginHostBinding.install_id == install_id,
                PluginHostBinding.host_id == host_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_binding(
        self,
        binding: PluginHostBinding,
    ) -> PluginHostBinding:
        self._session.add(binding)
        await self._session.flush()
        await self._session.refresh(binding)
        return binding

    async def delete_binding(self, binding: PluginHostBinding) -> None:
        await self._session.delete(binding)
