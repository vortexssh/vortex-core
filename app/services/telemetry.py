import json
from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis

from app.core.config import get_settings
from app.schemas.task import TelemetryRead


class TelemetryService:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._settings = get_settings()

    def _key(self, host_id: UUID) -> str:
        return f"telemetry:{host_id}"

    async def store(self, host_id: UUID, payload: dict) -> None:
        data = {
            **payload,
            "host_id": str(host_id),
            "collected_at": datetime.now(UTC).isoformat(),
        }
        await self._redis.set(
            self._key(host_id),
            json.dumps(data),
            ex=self._settings.telemetry_ttl_seconds,
        )

    async def get(self, host_id: UUID) -> TelemetryRead | None:
        raw = await self._redis.get(self._key(host_id))
        if raw is None:
            return None
        data = json.loads(raw)
        collected = data.get("collected_at")
        return TelemetryRead(
            host_id=UUID(data.get("host_id", str(host_id))),
            cpu_percent=data.get("cpu_percent"),
            ram_percent=data.get("ram_percent"),
            ram_used_bytes=data.get("ram_used_bytes"),
            ram_total_bytes=data.get("ram_total_bytes"),
            net_bytes_sent=data.get("net_bytes_sent"),
            net_bytes_recv=data.get("net_bytes_recv"),
            uptime_seconds=data.get("uptime_seconds"),
            collected_at=datetime.fromisoformat(collected) if collected else None,
        )

    async def get_many(self, host_ids: list[UUID]) -> list[TelemetryRead]:
        results: list[TelemetryRead] = []
        for host_id in host_ids:
            item = await self.get(host_id)
            if item is not None:
                results.append(item)
        return results
