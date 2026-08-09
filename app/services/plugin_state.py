"""Plugin live state in Redis only (never PostgreSQL)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from redis.asyncio import Redis

from app.core.config import get_settings
from app.schemas.plugin import PluginStateRead


class PluginStateService:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._settings = get_settings()

    def _global_key(self, install_id: UUID) -> str:
        return f"plugin:{install_id}:state"

    def _host_key(self, install_id: UUID, host_id: UUID) -> str:
        return f"plugin:{install_id}:host:{host_id}:state"

    def _history_key(
        self,
        install_id: UUID,
        host_id: UUID | None,
        history_key: str,
    ) -> str:
        if host_id is None:
            return f"plugin:{install_id}:history:{history_key}"
        return f"plugin:{install_id}:host:{host_id}:history:{history_key}"

    async def store(
        self,
        install_id: UUID,
        state: dict[str, Any],
        *,
        host_id: UUID | None = None,
        history_key: str | None = None,
    ) -> PluginStateRead:
        data = {
            **state,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        raw = json.dumps(data)
        key = (
            self._host_key(install_id, host_id)
            if host_id is not None
            else self._global_key(install_id)
        )
        ttl = self._settings.plugin_state_ttl_seconds
        pipe = self._redis.pipeline()
        pipe.set(key, raw, ex=ttl)
        if history_key:
            hist = self._history_key(install_id, host_id, history_key)
            pipe.lpush(hist, raw)
            pipe.ltrim(hist, 0, max(0, self._settings.plugin_history_size - 1))
            pipe.expire(hist, self._settings.plugin_history_ttl_seconds)
        await pipe.execute()
        return PluginStateRead(
            install_id=install_id,
            host_id=host_id,
            state=state,
            updated_at=data["updated_at"],
        )

    async def get(
        self,
        install_id: UUID,
        *,
        host_id: UUID | None = None,
    ) -> PluginStateRead:
        key = (
            self._host_key(install_id, host_id)
            if host_id is not None
            else self._global_key(install_id)
        )
        raw = await self._redis.get(key)
        if raw is None:
            return PluginStateRead(install_id=install_id, host_id=host_id, state={})
        data = json.loads(raw)
        updated = data.pop("updated_at", None)
        return PluginStateRead(
            install_id=install_id,
            host_id=host_id,
            state=data,
            updated_at=updated,
        )

    async def history(
        self,
        install_id: UUID,
        history_key: str,
        *,
        host_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        rows = await self._redis.lrange(
            self._history_key(install_id, host_id, history_key),
            0,
            -1,
        )
        if not rows:
            return []
        # Redis LPUSH → newest first; reverse for charts
        parsed = [json.loads(r) for r in reversed(rows)]
        return parsed
