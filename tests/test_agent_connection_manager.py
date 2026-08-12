from uuid import uuid4

import pytest
from starlette.websockets import WebSocketState

from app.websocket.manager import AgentConnectionManager


class _FakeWebSocket:
    def __init__(self) -> None:
        self.client_state = WebSocketState.CONNECTED
        self.closed = False

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed = True
        self.client_state = WebSocketState.DISCONNECTED


@pytest.mark.asyncio
async def test_disconnect_agent_ignores_stale_handler() -> None:
    manager = AgentConnectionManager()
    agent_id = uuid4()
    host_id = uuid4()
    old_ws = _FakeWebSocket()
    new_ws = _FakeWebSocket()

    await manager.connect_agent(
        agent_id=agent_id,
        host_id=host_id,
        websocket=old_ws,
    )
    await manager.connect_agent(
        agent_id=agent_id,
        host_id=host_id,
        websocket=new_ws,
    )
    assert old_ws.closed

    await manager.disconnect_agent(agent_id, websocket=old_ws)
    assert manager.get_local_agent(agent_id) is not None
    assert manager.get_local_agent(agent_id).websocket is new_ws

    await manager.disconnect_agent(agent_id, websocket=new_ws)
    assert manager.get_local_agent(agent_id) is None


@pytest.mark.asyncio
async def test_connect_agent_registers_before_closing_previous() -> None:
    manager = AgentConnectionManager()
    agent_id = uuid4()
    host_id = uuid4()
    old_ws = _FakeWebSocket()
    new_ws = _FakeWebSocket()

    await manager.connect_agent(
        agent_id=agent_id,
        host_id=host_id,
        websocket=old_ws,
    )
    await manager.connect_agent(
        agent_id=agent_id,
        host_id=host_id,
        websocket=new_ws,
    )

    assert manager.get_local_agent(agent_id).websocket is new_ws
    assert old_ws.closed
