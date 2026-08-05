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

    def _history_key(self, host_id: UUID) -> str:
        return f"telemetry:history:{host_id}"

    def _parse(self, data: dict, host_id: UUID) -> TelemetryRead:
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

    async def store(self, host_id: UUID, payload: dict) -> None:
        data = {
            **payload,
            "host_id": str(host_id),
            "collected_at": datetime.now(UTC).isoformat(),
        }
        raw = json.dumps(data)
        hist = self._history_key(host_id)
        pipe = self._redis.pipeline()
        pipe.set(self._key(host_id), raw, ex=self._settings.telemetry_ttl_seconds)
        pipe.lpush(hist, raw)
        pipe.ltrim(hist, 0, max(0, self._settings.telemetry_history_size - 1))
        pipe.expire(hist, self._settings.telemetry_history_ttl_seconds)
        await pipe.execute()

    async def get(self, host_id: UUID) -> TelemetryRead | None:
        raw = await self._redis.get(self._key(host_id))
        if raw is None:
            return None
        return self._parse(json.loads(raw), host_id)

    async def history(self, host_id: UUID) -> list[TelemetryRead]:
        """Oldest → newest (for charts)."""
        rows = await self._redis.lrange(self._history_key(host_id), 0, -1)
        if not rows:
            latest = await self.get(host_id)
            return [latest] if latest else []
        # LPUSH stores newest first
        parsed = [self._parse(json.loads(row), host_id) for row in reversed(rows)]
        return parsed

    async def get_many(self, host_ids: list[UUID]) -> list[TelemetryRead]:
        results: list[TelemetryRead] = []
        for host_id in host_ids:
            item = await self.get(host_id)
            if item is not None:
                results.append(item)
        return results
