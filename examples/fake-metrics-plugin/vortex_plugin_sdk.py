"""Minimal reusable helpers for Vortex out-of-process plugin daemons."""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

import httpx

RpcHandler = Callable[[str, dict[str, Any], str | None], Awaitable[dict[str, Any]]]


def plugin_ws_url(core_url: str, install_id: str, token: str) -> str:
    u = urlparse(core_url.rstrip("/"))
    scheme = "wss" if u.scheme == "https" else "ws"
    return f"{scheme}://{u.netloc}/ws/plugin/{install_id}?token={token}"


async def push_state(
    client: httpx.AsyncClient,
    *,
    core_url: str,
    install_id: str,
    token: str,
    state: dict[str, Any],
    host_id: str | None = None,
    history_key: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"state": state}
    if host_id:
        body["host_id"] = host_id
    if history_key:
        body["history_key"] = history_key
    r = await client.post(
        f"{core_url.rstrip('/')}/api/v1/plugins/{install_id}/daemon/state",
        json=body,
        headers={"X-Plugin-Token": token},
        timeout=30.0,
    )
    r.raise_for_status()
    return r.json()


def rpc_response(
    request_id: str,
    *,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> str:
    payload: dict[str, Any] = {"type": "rpc_response", "request_id": request_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result or {}
    return json.dumps(payload)
