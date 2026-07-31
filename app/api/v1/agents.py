from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession, UserWith2FA
from app.schemas.agent import AgentCreated, AgentRead, AgentRotateResponse
from app.services.agent import AgentService

router = APIRouter(tags=["agents"])


@router.post(
    "/hosts/{host_id}/agents",
    response_model=AgentCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent(
    host_id: UUID,
    user: UserWith2FA,
    session: DbSession,
) -> AgentCreated:
    service = AgentService(session)
    return await service.create_for_host(user.id, host_id)


@router.get("/hosts/{host_id}/agents", response_model=AgentRead)
async def get_agent(
    host_id: UUID,
    user: CurrentUser,
    session: DbSession,
) -> AgentRead:
    service = AgentService(session)
    agent = await service.get_for_host(user.id, host_id)
    return AgentRead.model_validate(agent)


@router.post(
    "/hosts/{host_id}/agents/rotate",
    response_model=AgentRotateResponse,
)
async def rotate_agent(
    host_id: UUID,
    user: UserWith2FA,
    session: DbSession,
) -> AgentRotateResponse:
    service = AgentService(session)
    return await service.rotate_secret(user.id, host_id)


@router.delete(
    "/hosts/{host_id}/agents",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_agent(
    host_id: UUID,
    user: UserWith2FA,
    session: DbSession,
) -> None:
    service = AgentService(session)
    await service.revoke(user.id, host_id)
