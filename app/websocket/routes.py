import json
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query, WebSocket, WebSocketException, status
from starlette.websockets import WebSocketDisconnect

from app.core.config import get_settings
from app.core.client_ip import websocket_client_ip
from app.core.database import AsyncSessionLocal
from app.core.rate_limit import rate_limiter
from app.core.redis import get_redis_client
from app.core.security import decode_access_token, verify_secret
from app.models.task import TaskLogStatus
from app.repositories.api_key import ApiKeyRepository
from app.repositories.host import HostRepository
from app.repositories.user import UserRepository
from app.services.agent import AgentService
from app.services.host import HostService
from app.services.plugin import PluginService
from app.services.task import TaskService
from app.services.telemetry import TelemetryService
from app.websocket.manager import connection_manager, pump_websocket_until_disconnect
from app.websocket.plugin_manager import plugin_connection_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


async def _resolve_user_from_token(token: str) -> Any:
    async with AsyncSessionLocal() as session:
        users = UserRepository(session)
        if token.startswith("vxk_"):
            api_keys = ApiKeyRepository(session)
            prefix = token[:12]
            for api_key in await api_keys.find_by_prefix(prefix):
                if api_keys.is_expired(api_key):
                    continue
                if verify_secret(token, api_key.key_hash):
                    user = await users.get_by_id(api_key.user_id)
                    if user and user.is_active:
                        return user
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
        try:
            payload = decode_access_token(token)
            user = await users.get_by_id(UUID(payload["sub"]))
        except (ValueError, KeyError) as exc:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION) from exc
        if user is None or not user.is_active:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
        return user


@router.websocket("/ws/agent")
async def agent_websocket(
    websocket: WebSocket,
    agent_id: UUID = Query(...),
    secret: str = Query(...),
    version: str | None = Query(default=None),
) -> None:
    settings = get_settings()
    client = websocket_client_ip(websocket) or "unknown"
    try:
        rate_limiter.check(
            f"agent-connect:{client}",
            limit=settings.agent_connect_rate_limit_per_minute,
        )
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    async with AsyncSessionLocal() as session:
        agent_service = AgentService(session)
        try:
            agent = await agent_service.authenticate(agent_id, secret)
        except Exception:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        host_id = agent.host_id

    await websocket.accept()
    redis = get_redis_client()
    await connection_manager.bind_redis(redis)

    peer_ip = websocket_client_ip(websocket)
    if peer_ip:
        async with AsyncSessionLocal() as session:
            try:
                await HostService(session).apply_geoip(host_id, peer_ip, redis)
            except Exception:
                logger.debug("GeoIP update failed for host %s", host_id, exc_info=True)

    async def on_presence(aid: UUID, online: bool, ver: str | None) -> None:
        async with AsyncSessionLocal() as session:
            service = AgentService(session)
            await service.set_online(aid, online=online, version=ver)

    async def on_telemetry(hid: UUID, payload: dict) -> None:
        clean = {
            k: payload.get(k)
            for k in (
                "cpu_percent",
                "ram_percent",
                "ram_used_bytes",
                "ram_total_bytes",
                "net_bytes_sent",
                "net_bytes_recv",
                "uptime_seconds",
            )
            if k in payload
        }
        await TelemetryService(redis).store(hid, clean)

    async def on_task_result(message: dict) -> None:
        try:
            task_id = UUID(message["task_id"])
            status_raw = str(message.get("status", "FAILED")).upper()
            status_value = TaskLogStatus(status_raw)
        except (KeyError, ValueError):
            logger.warning("Invalid task_result payload: %s", message)
            return
        async with AsyncSessionLocal() as session:
            service = TaskService(session)
            await service.record_result(
                task_id,
                status_value=status_value,
                exit_code=message.get("exit_code"),
                stdout=message.get("stdout"),
                stderr=message.get("stderr"),
            )

    connection_manager.on_presence = on_presence
    connection_manager.on_telemetry = on_telemetry
    connection_manager.on_task_result = on_task_result

    try:
        await connection_manager.connect_agent(
            agent_id=agent_id,
            host_id=host_id,
            websocket=websocket,
            version=version,
        )
        await websocket.send_json({"type": "connected", "agent_id": str(agent_id)})

        async def on_text(text: str) -> None:
            await connection_manager.handle_agent_message(agent_id, text)

        async def on_bytes(data: bytes) -> None:
            await connection_manager.handle_agent_message(agent_id, data)

        await pump_websocket_until_disconnect(websocket, on_text=on_text, on_bytes=on_bytes)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Agent websocket error for %s", agent_id)
    finally:
        try:
            await connection_manager.disconnect_agent(agent_id)
        except Exception:
            logger.debug("disconnect_agent failed", exc_info=True)


async def _authorize_host_tunnel(
    host_id: UUID,
    token: str,
    *,
    require_proxy: bool,
) -> tuple[Any, Any]:
    user = await _resolve_user_from_token(token)
    if not user.is_2fa_enabled:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="2FA required",
        )

    async with AsyncSessionLocal() as session:
        host = await HostRepository(session).get_by_id(host_id, user.id)
        if host is None:
            raise WebSocketException(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Host not found",
            )
        if require_proxy and not host.is_proxy_enabled:
            raise WebSocketException(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Proxy disabled",
            )
        if host.agent is None:
            raise WebSocketException(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="No agent",
            )
        agent_id = host.agent.id
        return user, agent_id


@router.websocket("/ws/plugin/{install_id}")
async def plugin_websocket(
    websocket: WebSocket,
    install_id: UUID,
    token: str = Query(...),
) -> None:
    """Out-of-process plugin daemon channel (presence + RPC)."""
    settings = get_settings()
    client = websocket_client_ip(websocket) or "unknown"
    try:
        rate_limiter.check(
            f"plugin-connect:{client}",
            limit=settings.plugin_connect_rate_limit_per_minute,
        )
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    if not token.startswith("vxp_"):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    async with AsyncSessionLocal() as session:
        service = PluginService(session)
        try:
            await service.authenticate_daemon(install_id, token)
        except Exception:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    await websocket.accept()
    try:
        await plugin_connection_manager.connect(install_id, websocket)
        async with AsyncSessionLocal() as session:
            await PluginService(session).set_daemon_online(install_id, True)
        await websocket.send_json(
            {"type": "connected", "install_id": str(install_id)}
        )

        async def on_text(text: str) -> None:
            try:
                message = json.loads(text)
            except json.JSONDecodeError:
                return
            if not isinstance(message, dict):
                return
            await plugin_connection_manager.handle_message(install_id, message)

        await pump_websocket_until_disconnect(websocket, on_text=on_text, on_bytes=None)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Plugin websocket error for %s", install_id)
    finally:
        try:
            await plugin_connection_manager.disconnect(install_id, websocket)
        except Exception:
            logger.debug("plugin disconnect failed", exc_info=True)
        try:
            async with AsyncSessionLocal() as session:
                await PluginService(session).set_daemon_online(install_id, False)
        except Exception:
            logger.debug("set_daemon_online failed", exc_info=True)


@router.websocket("/ws/proxy/{host_id}")
async def proxy_websocket(
    websocket: WebSocket,
    host_id: UUID,
    token: str = Query(...),
) -> None:
    _, agent_id = await _authorize_host_tunnel(host_id, token, require_proxy=True)

    if not await connection_manager.is_agent_online(agent_id):
        raise WebSocketException(
            code=status.WS_1013_TRY_AGAIN_LATER,
            reason="Agent offline",
        )

    await websocket.accept()
    session_id: str | None = None
    try:
        session_id = await connection_manager.open_client_session(
            kind="proxy",
            host_id=host_id,
            agent_id=agent_id,
            client_ws=websocket,
        )
        await websocket.send_json({"type": "proxy_ready", "session_id": session_id})

        async def on_bytes(data: bytes) -> None:
            assert session_id is not None
            await connection_manager.forward_client_bytes(
                session_id, data, kind="proxy"
            )

        async def on_text(text: str) -> None:
            assert session_id is not None
            await connection_manager.forward_client_bytes(
                session_id, text.encode("utf-8"), kind="proxy"
            )

        await pump_websocket_until_disconnect(
            websocket, on_text=on_text, on_bytes=on_bytes
        )
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Proxy websocket error for host %s", host_id)
    finally:
        if session_id:
            await connection_manager.close_client_session(session_id)


@router.websocket("/ws/pty/{host_id}")
async def pty_websocket(
    websocket: WebSocket,
    host_id: UUID,
    token: str = Query(...),
    cols: int = Query(default=80, ge=1, le=500),
    rows: int = Query(default=24, ge=1, le=200),
) -> None:
    _, agent_id = await _authorize_host_tunnel(host_id, token, require_proxy=False)

    if not await connection_manager.is_agent_online(agent_id):
        raise WebSocketException(
            code=status.WS_1013_TRY_AGAIN_LATER,
            reason="Agent offline",
        )

    await websocket.accept()
    session_id: str | None = None
    try:
        session_id = await connection_manager.open_client_session(
            kind="pty",
            host_id=host_id,
            agent_id=agent_id,
            client_ws=websocket,
            extra={"cols": cols, "rows": rows},
        )
        await websocket.send_json({"type": "pty_ready", "session_id": session_id})

        async def on_bytes(data: bytes) -> None:
            assert session_id is not None
            await connection_manager.forward_client_bytes(session_id, data, kind="pty")

        async def on_text(text: str) -> None:
            assert session_id is not None
            # Control: live PTY resize (do not treat as stdin).
            if text.startswith("{") and '"pty_resize"' in text:
                try:
                    msg = json.loads(text)
                    if msg.get("type") == "pty_resize":
                        await connection_manager.resize_pty_session(
                            session_id,
                            cols=int(msg["cols"]),
                            rows=int(msg["rows"]),
                        )
                        return
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    pass
            await connection_manager.forward_client_bytes(
                session_id, text.encode("utf-8"), kind="pty"
            )

        await pump_websocket_until_disconnect(
            websocket, on_text=on_text, on_bytes=on_bytes
        )
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("PTY websocket error for host %s", host_id)
    finally:
        if session_id:
            await connection_manager.close_client_session(session_id)
