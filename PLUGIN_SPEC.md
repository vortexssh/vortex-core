# Vortex Plugin Specification (`api_version: 1`)

Out-of-process **daemons** extend Vortex without shipping code inside Core or Web. Core is the gateway (auth, storage, RPC, UI bundle). Web renders **declarative** contributions into fixed slots.

**Для авторов демонов (подробный гайд):** [`docs/DAEMON_CREATORS.md`](docs/DAEMON_CREATORS.md).

## Package layout

```text
my-plugin/
  vortex-plugin.json      # required manifest
  ui/                     # optional files (may be inlined in manifest.views)
  schemas/                # optional JSON Schema files (may be inlined in manifest.schemas)
  README.md
```

For install via API/Web, either paste a self-contained `vortex-plugin.json` with inline `views` / `schemas`, or resolve file paths client-side before POST.

## Manifest

| Field | Required | Description |
|-------|----------|-------------|
| `id` | yes | Reverse-DNS id (`com.example.foo`) |
| `name` | yes | Display name |
| `version` | yes | Semver-ish string |
| `api_version` | yes | Must be `1` |
| `permissions` | yes | Capability list (see below) |
| `config_schema` | no | Install-level config schema (object or path key) |
| `host_binding_schema` | no | Per-host binding schema |
| `rpc` | no | Declared RPC methods `{ method, input?, output? }` |
| `ui.contributions` | no | UI slot contributions |
| `views` | no | Map path → declarative view tree |
| `schemas` | no | Map path → JSON Schema object |

### Permissions

| Permission | Allows |
|------------|--------|
| `host.bind` | Create/update host bindings |
| `state.write` | Daemon state push to Redis |
| `rpc` | User-triggered RPC to daemon |
| `nav` | `nav.items` slot |
| `pages` | `routes` slot |
| `hosts.columns` | `hosts.table.columns` |
| `hosts.panels` | `hosts.detail.panels` |
| `hosts.actions` | `hosts.row.actions` / `host.actions` |
| `hosts.editor` | `hosts.editor.fields` |
| `settings` | `settings.tabs` |

Contributions whose slot permission is missing are dropped from the UI bundle.

### UI slots

| Slot | Payload highlights |
|------|--------------------|
| `nav.items` | `item.label`, `item.route` (`plugin:{id}/path`) |
| `routes` | `route`, `view` |
| `hosts.table.columns` | `column.header`, `column.bind`, `column.unit` |
| `hosts.detail.panels` | `view`, optional `requires_host_binding` |
| `hosts.row.actions` / `host.actions` | `action` (RPC method) |
| `hosts.editor.fields` | JSON Schema for binding fields |
| `settings.tabs` | `label`, `view` |

Web routes resolve as `/plugins/{pluginId}/{path}`.

## Declarative UI DSL

Node `type` values: `stack`, `grid`, `tabs`, `panel`, `text`, `markdown`, `metric`, `badge`, `progress`, `sparkline`, `chart`, `table`, `form`, `button`, `confirm`, `repeater`.

Bindings:

- `host.*` — host metadata from Core
- `install.config` — install config
- `binding.config` — per-host binding
- `plugin.state` / `plugin.state.*` — Redis live state
- `action.result` — last RPC result in the view

Conditions: `visibleIf` / `enableIf` — path truthiness or `path == value`.

**Security:** no `eval`, no arbitrary HTML. Markdown is plain text in v1. Plugins never receive SSH passwords or private keys.

## Core API

Authenticated as the user (JWT / `vxk_` API key):

| Method | Path |
|--------|------|
| GET | `/api/v1/plugins` |
| POST | `/api/v1/plugins` body `{ manifest, config }` → includes one-time `daemon_token` |
| GET/PATCH/DELETE | `/api/v1/plugins/{install_id}` |
| POST | `/api/v1/plugins/{install_id}/rotate-token` |
| GET | `/api/v1/plugins/{install_id}/manifest` |
| GET | `/api/v1/plugins/ui-bundle` |
| PUT/DELETE | `/api/v1/plugins/{install_id}/bindings/{host_id}` |
| GET | `/api/v1/plugins/{install_id}/state?host_id=` |
| POST | `/api/v1/plugins/{install_id}/rpc/{method}` body `{ params, host_id? }` |

Daemon auth (`X-Plugin-Token: vxp_…` or WS query `token=`):

| Method | Path |
|--------|------|
| POST | `/api/v1/plugins/{install_id}/daemon/state` `{ state, host_id?, history_key? }` |
| WS | `/ws/plugin/{install_id}?token=vxp_…` |

### WebSocket messages

Daemon → Core: `heartbeat`, `rpc_response` `{ request_id, result | error }`.

Core → Daemon: `connected`, `rpc_request` `{ request_id, method, params, host_id? }`.

### Redis keys (TTL)

- `plugin:{install_id}:state`
- `plugin:{install_id}:host:{host_id}:state`
- optional history lists via `history_key`

Plugin telemetry/state is **never** written to PostgreSQL.

## Compatibility

- Core rejects `api_version != 1`.
- Unknown permissions / slots fail manifest validation.
- Additive DSL widgets may appear in later Core/Web releases; unknown `type` renders as “Unsupported widget” without crashing the shell.
- Breaking changes bump `api_version`.

## Reference implementation

See [`examples/fake-metrics-plugin/`](examples/fake-metrics-plugin/).
