from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.host import TagCreate, TagFullRead, TagUpdate
from app.services.host import TagService

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("", response_model=list[TagFullRead])
async def list_tags(user: CurrentUser, session: DbSession) -> list[TagFullRead]:
    service = TagService(session)
    tags = await service.list_tags(user.id)
    return [TagFullRead.model_validate(t) for t in tags]


@router.post("", response_model=TagFullRead, status_code=status.HTTP_201_CREATED)
async def create_tag(
    payload: TagCreate,
    user: CurrentUser,
    session: DbSession,
) -> TagFullRead:
    service = TagService(session)
    tag = await service.create_tag(user.id, payload)
    return TagFullRead.model_validate(tag)


@router.patch("/{tag_id}", response_model=TagFullRead)
async def update_tag(
    tag_id: UUID,
    payload: TagUpdate,
    user: CurrentUser,
    session: DbSession,
) -> TagFullRead:
    service = TagService(session)
    tag = await service.update_tag(user.id, tag_id, payload)
    return TagFullRead.model_validate(tag)


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    tag_id: UUID,
    user: CurrentUser,
    session: DbSession,
) -> None:
    service = TagService(session)
    await service.delete_tag(user.id, tag_id)
