from datetime import datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_api_key, hash_secret
from app.models.api_key import ApiKey
from app.repositories.api_key import ApiKeyRepository
from app.schemas.api_key import ApiKeyCreate, ApiKeyCreated


class ApiKeyService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = ApiKeyRepository(session)
        self._session = session

    async def list_keys(self, user_id: UUID) -> list[ApiKey]:
        return await self._repo.list_for_user(user_id)

    async def create(self, user_id: UUID, payload: ApiKeyCreate) -> ApiKeyCreated:
        raw = generate_api_key()
        api_key = ApiKey(
            user_id=user_id,
            name=payload.name,
            key_hash=hash_secret(raw),
            key_prefix=raw[:12],
            expires_at=payload.expires_at,
        )
        api_key = await self._repo.create(api_key)
        await self._session.commit()
        from app.models.billing import NotificationKind
        from app.services.notifications import notify_user

        await notify_user(
            self._session,
            user_id,
            kind=NotificationKind.API_KEY_CREATED,
            title="API key created",
            body=f"API key «{api_key.name}» was created ({api_key.key_prefix}…).",
        )
        return ApiKeyCreated(
            id=api_key.id,
            name=api_key.name,
            key_prefix=api_key.key_prefix,
            expires_at=api_key.expires_at,
            created_at=api_key.created_at,
            key=raw,
        )

    async def delete(self, user_id: UUID, key_id: UUID) -> None:
        api_key = await self._repo.get_by_id(key_id, user_id)
        if api_key is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "api_key_not_found", "message": "API key not found"},
            )
        name = api_key.name
        await self._repo.delete(api_key)
        await self._session.commit()
        from app.models.billing import NotificationKind
        from app.services.notifications import notify_user

        await notify_user(
            self._session,
            user_id,
            kind=NotificationKind.API_KEY_DELETED,
            title="API key deleted",
            body=f"API key «{name}» was deleted.",
        )
