#!/usr/bin/env python3
"""Reference Vortex plugin daemon (Fake Metrics).

Environment:
  VORTEX_CORE_URL   e.g. https://api.example.com  (no trailing slash)
  VORTEX_INSTALL_ID UUID of the plugin install
  VORTEX_DAEMON_TOKEN  vxp_… token shown once at install
  VORTEX_INTERVAL   seconds between state pushes (default 10)
  VORTEX_HOST_ID    optional host UUID to also publish per-host state

Install the manifest via Settings → Plugins (or POST /api/v1/plugins),
then run this process outbound to Core (NAT-friendly).
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import sys
from typing import Any
from urllib.parse import urlparse

import httpx

try:
    import websockets
except ImportError:
    print("Install deps: pip install httpx websockets", file=sys.stderr)
    raise


class FakeMetricsDaemon:
    def __init__(self) -> None:
        self.core_url = os.environ["VORTEX_CORE_URL"].rstrip("/")
        self.install_id = os.environ["VORTEX_INSTALL_ID"]
        self.token = os.environ["VORTEX_DAEMON_TOKEN"]
        self.interval = int(os.environ.get("VORTEX_INTERVAL", "10"))
        self.host_id = os.environ.get("VORTEX_HOST_ID") or None
        self.value = 0.0

    def _ws_url(self) -> str:
        u = urlparse(self.core_url)
        scheme = "wss" if u.scheme == "https" else "ws"
        return (
            f"{scheme}://{u.netloc}/ws/plugin/{self.install_id}"
            f"?token={self.token}"
        )

    async def push_state(self, client: httpx.AsyncClient, state: dict[str, Any]) -> None:
        path = f"/api/v1/plugins/{self.install_id}/daemon/state"
        body: dict[str, Any] = {"state": state, "history_key": "value"}
        if self.host_id:
            body["host_id"] = self.host_id
        r = await client.post(
            self.core_url + path,
            json=body,
            headers={"X-Plugin-Token": self.token},
            timeout=30.0,
        )
        r.raise_for_status()

    async def handle_rpc(self, message: dict[str, Any], ws: Any) -> None:
        method = message.get("method")
        request_id = message.get("request_id")
        if method == "bump":
            self.value += 1
        elif method == "refresh":
            pass
        else:
            await ws.send(
                json.dumps(
                    {
                        "type": "rpc_response",
                        "request_id": request_id,
                        "error": f"unknown method: {method}",
                    }
                )
            )
            return
        result = {"value": self.value}
        await ws.send(
            json.dumps(
                {
                    "type": "rpc_response",
                    "request_id": request_id,
                    "result": result,
                }
            )
        )

    async def run(self) -> None:
        async with httpx.AsyncClient() as client:
            while True:
                try:
                    async with websockets.connect(
                        self._ws_url(),
                        ping_interval=20,
                        ping_timeout=20,
                    ) as ws:
                        print("connected to Core plugin channel", flush=True)
                        hello = json.loads(await ws.recv())
                        print("core:", hello, flush=True)

                        async def publisher() -> None:
                            while True:
                                self.value += random.uniform(0.1, 1.5)
                                await self.push_state(
                                    client, {"value": round(self.value, 2)}
                                )
                                await asyncio.sleep(self.interval)

                        pub_task = asyncio.create_task(publisher())
                        try:
                            async for raw in ws:
                                try:
                                    msg = json.loads(raw)
                                except json.JSONDecodeError:
                                    continue
                                if msg.get("type") == "rpc_request":
                                    await self.handle_rpc(msg, ws)
                                    # also refresh redis after RPC
                                    await self.push_state(
                                        client, {"value": round(self.value, 2)}
                                    )
                                elif msg.get("type") == "heartbeat":
                                    await ws.send(json.dumps({"type": "heartbeat"}))
                        finally:
                            pub_task.cancel()
                            try:
                                await pub_task
                            except asyncio.CancelledError:
                                pass
                except Exception as exc:
                    print(f"disconnected: {exc}; retry in 5s", flush=True)
                    await asyncio.sleep(5)


def main() -> None:
    required = ("VORTEX_CORE_URL", "VORTEX_INSTALL_ID", "VORTEX_DAEMON_TOKEN")
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        print(f"Missing env: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)
    asyncio.run(FakeMetricsDaemon().run())


if __name__ == "__main__":
    main()
