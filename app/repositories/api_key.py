from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import ApiKey


class ApiKeyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user(self, user_id: UUID) -> list[ApiKey]:
        result = await self._session.execute(
            select(ApiKey)
            .where(ApiKey.user_id == user_id)
            .order_by(ApiKey.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, key_id: UUID, user_id: UUID) -> ApiKey | None:
        result = await self._session.execute(
            select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def find_by_prefix(self, prefix: str) -> list[ApiKey]:
        result = await self._session.execute(
            select(ApiKey).where(ApiKey.key_prefix == prefix)
        )
        return list(result.scalars().all())

    async def create(self, api_key: ApiKey) -> ApiKey:
        self._session.add(api_key)
        await self._session.flush()
        await self._session.refresh(api_key)
        return api_key

    async def delete(self, api_key: ApiKey) -> None:
        await self._session.delete(api_key)
        await self._session.flush()

    @staticmethod
    def is_expired(api_key: ApiKey) -> bool:
        if api_key.expires_at is None:
            return False
        expires = api_key.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        return expires < datetime.now(UTC)
