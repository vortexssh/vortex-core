from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.api_key import ApiKeyCreate, ApiKeyCreated, ApiKeyRead
from app.services.api_key import ApiKeyService

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


@router.get("", response_model=list[ApiKeyRead])
async def list_api_keys(user: CurrentUser, session: DbSession) -> list[ApiKeyRead]:
    service = ApiKeyService(session)
    keys = await service.list_keys(user.id)
    return [ApiKeyRead.model_validate(k) for k in keys]


@router.post("", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: ApiKeyCreate,
    user: CurrentUser,
    session: DbSession,
) -> ApiKeyCreated:
    service = ApiKeyService(session)
    return await service.create(user.id, payload)


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    key_id: UUID,
    user: CurrentUser,
    session: DbSession,
) -> None:
    service = ApiKeyService(session)
    await service.delete(user.id, key_id)
