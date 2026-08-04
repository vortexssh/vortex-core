"""WebSocket Tunnel Router: agent registry, TCP/SSH proxy, PTY bridging."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from fastapi import WebSocket
from redis.asyncio import Redis
from starlette.websockets import WebSocketDisconnect, WebSocketState

from app.core.config import get_settings

logger = logging.getLogger(__name__)

TaskResultHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]
TelemetryHandler = Callable[[UUID, dict[str, Any]], Coroutine[Any, Any, None]]
PresenceHandler = Callable[[UUID, bool, str | None], Coroutine[Any, Any, None]]


@dataclass
class ClientSession:
    session_id: str
    kind: str  # proxy | pty
    client_ws: WebSocket
    agent_id: UUID
    host_id: UUID


@dataclass
class AgentConnection:
    agent_id: UUID
    host_id: UUID
    websocket: WebSocket
    sessions: dict[str, ClientSession] = field(default_factory=dict)


class AgentConnectionManager:
    """In-memory agent sockets + Redis presence; Pub/Sub ready for multi-worker."""

    def __init__(self) -> None:
        self._agents: dict[UUID, AgentConnection] = {}
        self._sessions: dict[str, ClientSession] = {}
        self._lock = asyncio.Lock()
        self._redis: Redis | None = None
        self._pubsub_task: asyncio.Task[None] | None = None
        self._worker_id: str = str(uuid4())
        self.on_telemetry: TelemetryHandler | None = None
        self.on_task_result: TaskResultHandler | None = None
        self.on_presence: PresenceHandler | None = None

    async def bind_redis(self, redis: Redis) -> None:
        self._redis = redis
        if self._pubsub_task is None:
            self._pubsub_task = asyncio.create_task(self._pubsub_loop())

    async def shutdown(self) -> None:
        if self._pubsub_task is not None:
            self._pubsub_task.cancel()
            try:
                await self._pubsub_task
            except asyncio.CancelledError:
                pass
            self._pubsub_task = None

    def _presence_key(self, agent_id: UUID) -> str:
        return f"agent:presence:{agent_id}"

    def _route_channel(self, agent_id: UUID) -> str:
        return f"agent:route:{agent_id}"

    async def connect_agent(
        self,
        *,
        agent_id: UUID,
        host_id: UUID,
        websocket: WebSocket,
        version: str | None = None,
    ) -> None:
        async with self._lock:
            existing = self._agents.get(agent_id)
            if existing is not None:
                try:
                    await existing.websocket.close(code=4000, reason="Replaced by new connection")
                except Exception:
                    logger.debug("Failed closing previous agent socket", exc_info=True)
            self._agents[agent_id] = AgentConnection(
                agent_id=agent_id,
                host_id=host_id,
                websocket=websocket,
            )

        settings = get_settings()
        if self._redis is not None:
            await self._redis.set(
                self._presence_key(agent_id),
                json.dumps(
                    {
                        "worker_id": self._worker_id,
                        "host_id": str(host_id),
                        "version": version,
                    }
                ),
                ex=settings.agent_presence_ttl_seconds,
            )
        if self.on_presence:
            await self.on_presence(agent_id, True, version)

    async def disconnect_agent(self, agent_id: UUID) -> None:
        async with self._lock:
            conn = self._agents.pop(agent_id, None)
            if conn is not None:
                for session_id in list(conn.sessions.keys()):
                    self._sessions.pop(session_id, None)

        if self._redis is not None:
            await self._redis.delete(self._presence_key(agent_id))
        if self.on_presence:
            await self.on_presence(agent_id, False, None)

    async def refresh_presence(self, agent_id: UUID) -> None:
        if self._redis is None:
            return
        settings = get_settings()
        key = self._presence_key(agent_id)
        raw = await self._redis.get(key)
        if raw:
            await self._redis.expire(key, settings.agent_presence_ttl_seconds)

    def get_local_agent(self, agent_id: UUID) -> AgentConnection | None:
        return self._agents.get(agent_id)

    async def is_agent_online(self, agent_id: UUID) -> bool:
        if agent_id in self._agents:
            return True
        if self._redis is None:
            return False
        return bool(await self._redis.exists(self._presence_key(agent_id)))

    async def open_client_session(
        self,
        *,
        kind: str,
        host_id: UUID,
        agent_id: UUID,
        client_ws: WebSocket,
        extra: dict[str, Any] | None = None,
    ) -> str:
        session_id = str(uuid4())
        session = ClientSession(
            session_id=session_id,
            kind=kind,
            client_ws=client_ws,
            agent_id=agent_id,
            host_id=host_id,
        )
        async with self._lock:
            self._sessions[session_id] = session
            local = self._agents.get(agent_id)
            if local is not None:
                local.sessions[session_id] = session

        message = {
            "type": f"{kind}_open",
            "session_id": session_id,
            "host_id": str(host_id),
            **(extra or {}),
        }
        await self._send_to_agent(agent_id, message)
        return session_id

    async def close_client_session(self, session_id: str, *, notify_agent: bool = True) -> None:
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            if session is not None:
                local = self._agents.get(session.agent_id)
                if local is not None:
                    local.sessions.pop(session_id, None)

        if session is None:
            return
        if notify_agent:
            await self._send_to_agent(
                session.agent_id,
                {
                    "type": f"{session.kind}_close",
                    "session_id": session_id,
                },
            )
        if session.client_ws.client_state == WebSocketState.CONNECTED:
            try:
                await session.client_ws.close()
            except Exception:
                logger.debug("Failed closing client session socket", exc_info=True)

    async def forward_client_bytes(
        self,
        session_id: str,
        data: bytes,
        *,
        kind: str,
    ) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        # Prefer binary frame to agent as JSON control + base64 is heavy;
        # use JSON envelope with base64 for protocol simplicity across languages.
        import base64

        await self._send_to_agent(
            session.agent_id,
            {
                "type": f"{kind}_data",
                "session_id": session_id,
                "encoding": "base64",
                "data": base64.b64encode(data).decode("ascii"),
            },
        )

    async def resize_pty_session(
        self,
        session_id: str,
        *,
        cols: int,
        rows: int,
    ) -> None:
        """Tell the agent to apply TIOCSWINSZ for an active PTY session."""
        session = self._sessions.get(session_id)
        if session is None or session.kind != "pty":
            return
        if cols < 1 or rows < 1:
            return
        await self._send_to_agent(
            session.agent_id,
            {
                "type": "pty_resize",
                "session_id": session_id,
                "cols": cols,
                "rows": rows,
            },
        )

    async def send_task_run(
        self,
        agent_id: UUID,
        *,
        task_id: UUID,
        command: str,
    ) -> bool:
        return await self._send_to_agent(
            agent_id,
            {
                "type": "task_run",
                "task_id": str(task_id),
                "command": command,
            },
        )

    async def handle_agent_message(self, agent_id: UUID, raw: str | bytes) -> None:
        try:
            if isinstance(raw, bytes):
                text = raw.decode("utf-8")
            else:
                text = raw
            message = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.warning("Invalid agent message from %s", agent_id)
            return

        msg_type = message.get("type")
        if msg_type == "telemetry":
            conn = self._agents.get(agent_id)
            if conn and self.on_telemetry:
                await self.on_telemetry(conn.host_id, message.get("payload") or message)
            return

        if msg_type == "heartbeat":
            await self.refresh_presence(agent_id)
            return

        if msg_type == "task_result":
            if self.on_task_result:
                await self.on_task_result(message)
            return

        if msg_type in {"proxy_data", "pty_data"}:
            await self._deliver_to_client(message)
            return

        if msg_type in {"proxy_close", "pty_close", "proxy_error", "pty_error"}:
            session_id = message.get("session_id")
            if session_id:
                await self.close_client_session(session_id, notify_agent=False)
            return

    async def _deliver_to_client(self, message: dict[str, Any]) -> None:
        import base64

        session_id = message.get("session_id")
        if not session_id:
            return
        session = self._sessions.get(session_id)
        if session is None:
            return
        try:
            if message.get("encoding") == "base64" and "data" in message:
                payload = base64.b64decode(message["data"])
                await session.client_ws.send_bytes(payload)
            elif "data" in message:
                data = message["data"]
                if isinstance(data, str):
                    await session.client_ws.send_text(data)
                else:
                    await session.client_ws.send_json(message)
            else:
                await session.client_ws.send_json(message)
        except Exception:
            logger.debug("Failed delivering to client session %s", session_id, exc_info=True)
            await self.close_client_session(session_id)

    async def _send_to_agent(self, agent_id: UUID, message: dict[str, Any]) -> bool:
        local = self._agents.get(agent_id)
        if local is not None:
            try:
                if local.websocket.client_state == WebSocketState.CONNECTED:
                    await local.websocket.send_json(message)
                    return True
            except Exception:
                logger.debug("Failed sending to local agent %s", agent_id, exc_info=True)
                return False

        # Cross-worker: publish via Redis Pub/Sub
        if self._redis is not None:
            await self._redis.publish(
                self._route_channel(agent_id),
                json.dumps({"worker_id": self._worker_id, "message": message}),
            )
            return True
        return False

    async def _pubsub_loop(self) -> None:
        if self._redis is None:
            return
        pubsub = self._redis.pubsub()
        await pubsub.psubscribe("agent:route:*")
        try:
            async for item in pubsub.listen():
                if item is None or item.get("type") not in {"pmessage", "message"}:
                    continue
                try:
                    payload = json.loads(item["data"])
                except (TypeError, json.JSONDecodeError):
                    continue
                if payload.get("worker_id") == self._worker_id:
                    continue
                channel = item.get("channel") or ""
                if isinstance(channel, bytes):
                    channel = channel.decode()
                try:
                    agent_id = UUID(channel.rsplit(":", 1)[-1])
                except ValueError:
                    continue
                local = self._agents.get(agent_id)
                if local is None:
                    continue
                try:
                    await local.websocket.send_json(payload["message"])
                except Exception:
                    logger.debug("PubSub forward failed for %s", agent_id, exc_info=True)
        except asyncio.CancelledError:
            await pubsub.punsubscribe("agent:route:*")
            await pubsub.aclose()
            raise
        except Exception:
            logger.exception("Agent pubsub loop crashed")


connection_manager = AgentConnectionManager()


async def pump_websocket_until_disconnect(
    websocket: WebSocket,
    on_text: Callable[[str], Coroutine[Any, Any, None]] | None = None,
    on_bytes: Callable[[bytes], Coroutine[Any, Any, None]] | None = None,
) -> None:
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if "text" in message and on_text:
                await on_text(message["text"])
            elif "bytes" in message and on_bytes:
                await on_bytes(message["bytes"])
    except WebSocketDisconnect:
        return
    except Exception:
        logger.debug("WebSocket pump ended with error", exc_info=True)
