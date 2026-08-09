"""In-memory plugin daemon WebSocket registry + RPC request/response."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from fastapi import WebSocket
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)


@dataclass
class PluginConnection:
    install_id: UUID
    websocket: WebSocket
    pending: dict[str, asyncio.Future[dict[str, Any]]] = field(default_factory=dict)


class PluginConnectionManager:
    def __init__(self) -> None:
        self._plugins: dict[UUID, PluginConnection] = {}
        self._lock = asyncio.Lock()

    def is_online(self, install_id: UUID) -> bool:
        conn = self._plugins.get(install_id)
        if conn is None:
            return False
        return conn.websocket.client_state == WebSocketState.CONNECTED

    async def connect(self, install_id: UUID, websocket: WebSocket) -> None:
        async with self._lock:
            existing = self._plugins.get(install_id)
            if existing is not None:
                for fut in existing.pending.values():
                    if not fut.done():
                        fut.set_exception(RuntimeError("Plugin connection replaced"))
                try:
                    await existing.websocket.close(
                        code=4000, reason="Replaced by new connection"
                    )
                except Exception:
                    logger.debug("Failed closing previous plugin socket", exc_info=True)
            self._plugins[install_id] = PluginConnection(
                install_id=install_id,
                websocket=websocket,
            )

    async def disconnect(self, install_id: UUID, websocket: WebSocket) -> None:
        async with self._lock:
            current = self._plugins.get(install_id)
            if current is None or current.websocket is not websocket:
                return
            for fut in current.pending.values():
                if not fut.done():
                    fut.set_exception(RuntimeError("Plugin disconnected"))
            del self._plugins[install_id]

    async def handle_message(self, install_id: UUID, message: dict[str, Any]) -> None:
        msg_type = message.get("type")
        if msg_type == "rpc_response":
            request_id = str(message.get("request_id", ""))
            conn = self._plugins.get(install_id)
            if conn is None:
                return
            fut = conn.pending.pop(request_id, None)
            if fut is None or fut.done():
                return
            if message.get("error"):
                fut.set_exception(RuntimeError(str(message["error"])))
            else:
                result = message.get("result")
                if not isinstance(result, dict):
                    result = {"value": result}
                fut.set_result(result)
            return
        if msg_type == "heartbeat":
            return
        logger.debug("Unhandled plugin message type=%s install=%s", msg_type, install_id)

    async def rpc(
        self,
        install_id: UUID,
        method: str,
        params: dict[str, Any],
        *,
        host_id: UUID | None = None,
        timeout: float = 15.0,
    ) -> dict[str, Any]:
        conn = self._plugins.get(install_id)
        if conn is None or conn.websocket.client_state != WebSocketState.CONNECTED:
            raise RuntimeError("Plugin daemon offline")

        request_id = str(uuid4())
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict[str, Any]] = loop.create_future()
        conn.pending[request_id] = fut
        payload: dict[str, Any] = {
            "type": "rpc_request",
            "request_id": request_id,
            "method": method,
            "params": params,
        }
        if host_id is not None:
            payload["host_id"] = str(host_id)
        try:
            await conn.websocket.send_text(json.dumps(payload))
            return await asyncio.wait_for(fut, timeout=timeout)
        except Exception:
            conn.pending.pop(request_id, None)
            raise


plugin_connection_manager = PluginConnectionManager()
