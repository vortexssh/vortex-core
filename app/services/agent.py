from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_agent_secret, hash_secret
from app.models.agent import Agent
from app.repositories.agent import AgentRepository
from app.repositories.host import HostRepository
from app.schemas.agent import AgentCreated, AgentRotateResponse


class AgentService:
    def __init__(self, session: AsyncSession) -> None:
        self._agents = AgentRepository(session)
        self._hosts = HostRepository(session)
        self._session = session

    async def create_for_host(self, user_id: UUID, host_id: UUID) -> AgentCreated:
        host = await self._hosts.get_by_id(host_id, user_id)
        if host is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "host_not_found", "message": "Host not found"},
            )
        existing = await self._agents.get_by_host_id(host_id)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "agent_exists",
                    "message": "Agent already exists for this host; rotate or revoke first",
                },
            )
        raw = generate_agent_secret()
        agent = Agent(host_id=host_id, secret_hash=hash_secret(raw))
        agent = await self._agents.create(agent)
        await self._session.commit()
        from app.models.billing import NotificationKind
        from app.services.notifications import notify_user

        await notify_user(
            self._session,
            user_id,
            kind=NotificationKind.AGENT_CREATED,
            title="Agent enrolled",
            body=f"A new agent was enrolled for host «{host.name}».",
            host_id=host_id,
        )
        return AgentCreated(
            id=agent.id,
            host_id=agent.host_id,
            secret=raw,
            version=agent.version,
            is_online=agent.is_online,
        )

    async def get_for_host(self, user_id: UUID, host_id: UUID) -> Agent:
        agent = await self._agents.get_for_user_host(host_id, user_id)
        if agent is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "agent_not_found", "message": "Agent not found"},
            )
        return agent

    async def rotate_secret(self, user_id: UUID, host_id: UUID) -> AgentRotateResponse:
        agent = await self.get_for_host(user_id, host_id)
        raw = generate_agent_secret()
        agent.secret_hash = hash_secret(raw)
        agent.is_online = False
        await self._agents.save(agent)
        await self._session.commit()
        from app.models.billing import NotificationKind
        from app.services.notifications import notify_user

        await notify_user(
            self._session,
            user_id,
            kind=NotificationKind.AGENT_ROTATED,
            title="Agent secret rotated",
            body="Agent credentials were rotated — reinstall with the new secret.",
            host_id=host_id,
        )
        return AgentRotateResponse(id=agent.id, host_id=agent.host_id, secret=raw)

    async def revoke(self, user_id: UUID, host_id: UUID) -> None:
        agent = await self.get_for_host(user_id, host_id)
        await self._agents.delete(agent)
        await self._session.commit()
        from app.models.billing import NotificationKind
        from app.services.notifications import notify_user

        await notify_user(
            self._session,
            user_id,
            kind=NotificationKind.AGENT_REVOKED,
            title="Agent revoked",
            body="An agent was revoked from one of your hosts.",
            host_id=host_id,
        )

    async def set_online(
        self,
        agent_id: UUID,
        *,
        online: bool,
        version: str | None = None,
    ) -> Agent | None:
        agent = await self._agents.get_by_id(agent_id)
        if agent is None:
            return None
        agent.is_online = online
        agent.last_seen_at = datetime.now(UTC)
        if version is not None:
            agent.version = version
        await self._agents.save(agent)
        await self._session.commit()
        return agent

    async def authenticate(self, agent_id: UUID, secret: str) -> Agent:
        from app.core.security import verify_secret

        agent = await self._agents.get_by_id(agent_id)
        if agent is None or not verify_secret(secret, agent.secret_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "invalid_agent_credentials", "message": "Invalid agent credentials"},
            )
        return agent
