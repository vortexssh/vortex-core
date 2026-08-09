# Fake Metrics (reference plugin)

Подробное руководство для авторов: [`../../docs/DAEMON_CREATORS.md`](../../docs/DAEMON_CREATORS.md).

Neutral example daemon for the Vortex plugin platform. It does **not** talk to Home Assistant or any smart plug — it only publishes a random counter so you can verify:

- install + daemon token
- WebSocket `/ws/plugin/{install_id}`
- state push to Redis
- RPC from Web UI
- declarative nav / page / host column / host panel / settings tab

## Install

1. Open Vortex Web → **Settings → Plugins**.
2. Paste [`vortex-plugin.json`](./vortex-plugin.json) (or use the sample already in the UI).
3. Copy the one-time `vxp_…` daemon token.

Alternatively:

```bash
curl -sS -X POST "$CORE/api/v1/plugins" \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d "{\"manifest\": $(cat vortex-plugin.json), \"config\": {\"interval_seconds\": 10}}"
```

## Run daemon

```bash
pip install httpx websockets
export VORTEX_CORE_URL=https://api.vortex.example
export VORTEX_INSTALL_ID=<uuid from install response>
export VORTEX_DAEMON_TOKEN=vxp_…
# optional: also publish per-host state
# export VORTEX_HOST_ID=<host uuid>
python daemon.py
```

The process connects outbound (works behind NAT), heartbeats on the plugin WS, pushes `{"value": …}` via `POST …/daemon/state`, and answers RPC methods `refresh` / `bump`.
