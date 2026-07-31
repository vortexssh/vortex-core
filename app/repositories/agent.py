from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.agent import Agent
from app.models.host import Host


class AgentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, agent_id: UUID) -> Agent | None:
        result = await self._session.execute(
            select(Agent)
            .options(selectinload(Agent.host))
            .where(Agent.id == agent_id)
        )
        return result.scalar_one_or_none()

    async def get_by_host_id(self, host_id: UUID) -> Agent | None:
        result = await self._session.execute(
            select(Agent).where(Agent.host_id == host_id)
        )
        return result.scalar_one_or_none()

    async def get_for_user_host(
        self,
        host_id: UUID,
        user_id: UUID,
    ) -> Agent | None:
        result = await self._session.execute(
            select(Agent)
            .join(Host, Agent.host_id == Host.id)
            .where(Agent.host_id == host_id, Host.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def create(self, agent: Agent) -> Agent:
        self._session.add(agent)
        await self._session.flush()
        await self._session.refresh(agent)
        return agent

    async def save(self, agent: Agent) -> Agent:
        self._session.add(agent)
        await self._session.flush()
        await self._session.refresh(agent)
        return agent

    async def delete(self, agent: Agent) -> None:
        await self._session.delete(agent)
        await self._session.flush()
