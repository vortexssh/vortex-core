"""Public status page — unauthenticated host telemetry snapshot."""

from uuid import UUID

from fastapi import HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.host import HostRepository
from app.repositories.user import UserRepository
from app.schemas.public import PublicHost, PublicStatusPage, PublicTelemetry
from app.services.telemetry import TelemetryService


class PublicStatusService:
    def __init__(self, session: AsyncSession, redis: Redis) -> None:
        self._users = UserRepository(session)
        self._hosts = HostRepository(session)
        self._telemetry = TelemetryService(redis)

    async def get_page(self, slug: str) -> PublicStatusPage:
        normalized = slug.strip().lower()
        user = await self._users.get_by_public_slug(normalized)
        if user is None or not user.is_active or user.public_slug is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "status_not_found", "message": "Status page not found"},
            )

        hosts = await self._hosts.list_public_for_user(user.id)
        host_ids = [h.id for h in hosts]
        telemetry_list = await self._telemetry.get_many(host_ids)
        by_host: dict[UUID, PublicTelemetry] = {
            t.host_id: PublicTelemetry(
                cpu_percent=t.cpu_percent,
                ram_percent=t.ram_percent,
                net_bytes_sent=t.net_bytes_sent,
                net_bytes_recv=t.net_bytes_recv,
                uptime_seconds=t.uptime_seconds,
                collected_at=t.collected_at,
            )
            for t in telemetry_list
        }

        public_hosts = [
            PublicHost(
                id=h.id,
                name=h.name,
                country_code=h.country_code,
                agent_online=bool(h.agent and h.agent.is_online),
                telemetry=by_host.get(h.id),
            )
            for h in hosts
        ]
        return PublicStatusPage(slug=user.public_slug, hosts=public_hosts)
