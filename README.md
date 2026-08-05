# Vortex Core

Бэкенд экосистемы **VortexSSH**: облачная записная книжка метаданных хостов и транзитный WebSocket Tunnel Router для обхода NAT / Web-терминала.

Клиенты (GUI/TUI) и хост-агенты (Go) работают через этот сервис. Сам Core **никогда** не хранит пароли целевых серверов и приватные SSH-ключи пользователей — только метаданные.

## Возможности

| Функция | Описание |
|---|---|
| **REST API** | Auth (JWT + TOTP), API keys, hosts, tags, agents, tasks |
| **WebSocket Tunnel Router** | Agent WSS, TCP/SSH proxy, PTY для WebSSH |
| **Телеметрия** | CPU/RAM и т.п. только в Redis (TTL), не в PostgreSQL |
| **2FA enforcement** | Телеметрия, WebSSH, proxy, tasks — только при `is_2fa_enabled` |

## Стек

- Python 3.11+
- FastAPI (async)
- PostgreSQL + SQLAlchemy 2.0 + asyncpg
- Redis (redis-py async)
- Alembic
- JWT + TOTP
- APScheduler (cron dispatch)

## Быстрый старт (локально)

```bash
# Только Postgres + Redis
docker compose -f docker-compose.dev.yml up -d

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Продакшен-деплой** (Docker + Nginx/HTTPS): см. [DEPLOY.md](DEPLOY.md).

- Health: `GET /api/v1/health`
- OpenAPI: `/docs`

## Структура

```
app/
├── main.py
├── core/           # config, DB, Redis, security, errors, rate limit
├── models/         # users, api_keys, hosts, tags, agents, tasks
├── schemas/        # Pydantic DTO
├── repositories/
├── services/
├── api/v1/         # REST routers
└── websocket/      # Tunnel Router
alembic/
docker-compose.yml
```

## REST (префикс `/api/v1`)

| Группа | Эндпоинты |
|---|---|
| Auth | `POST /auth/register`, `/auth/login`, `/auth/verify-email`, `/auth/resend-verification`, `/auth/2fa/setup\|verify\|disable`, `/auth/password` |
| Users | `GET/PATCH /users/me` (profile, `public_slug`, `preferred_currency`), notification-settings, telegram link |
| Billing | `GET /billing/summary`, `/billing/calendar`, `POST /hosts/{id}/billing/advance` |
| Notifications | `GET /notifications`, mark read / read-all; inbox for Web + TUI (`client` channel) |
| Public | `GET /public/u/{slug}` — status page (no auth, no IPs) |
| API keys | `GET/POST /api-keys`, `DELETE /api-keys/{id}` |
| Hosts | CRUD `/hosts`, `PATCH .../proxy`, `PATCH .../hidden`, tags |
| Telemetry | `GET /hosts/{id}/telemetry` (2FA) |
| Tags | CRUD `/tags` |
| Agents | `POST/GET/DELETE /hosts/{id}/agents`, `POST .../rotate` (2FA на create/rotate/revoke) |
| Tasks | CRUD + `POST /tasks/{id}/run`, `GET /tasks/{id}/logs` (2FA) |

Авторизация: `Authorization: Bearer <jwt|vxk_...>` или `X-API-Key: vxk_...`.

## WebSocket

| Endpoint | Auth | Назначение |
|---|---|---|
| `WS /ws/agent?agent_id=&secret=&version=` | agent secret | Постоянное соединение агента |
| `WS /ws/proxy/{host_id}?token=` | JWT/API key + 2FA + `is_proxy_enabled` | Сырой TCP/SSH туннель |
| `WS /ws/pty/{host_id}?token=&cols=&rows=` | JWT/API key + 2FA | Web-терминал (PTY) |

### Кадры агента (JSON)

- `telemetry` — `{ "type": "telemetry", "cpu_percent": ..., ... }`
- `heartbeat` — продлевает Redis presence
- `proxy_open` / `proxy_data` / `proxy_close` (от Core к агенту и обратно)
- `pty_open` / `pty_data` / `pty_close`
- `task_run` / `task_result` (`status`: SUCCESS\|FAILED\|TIMEOUT)

Бинарные данные в `*_data` передаются как `encoding: base64`.

## Безопасность

1. **Zero-trust** — схемы hosts отвергают `password` / `private_key` / и т.п.
2. **2FA** — dependency `require_2fa` на agent-facing REST и WS proxy/pty.
3. **No DB metrics** — только Redis ключ `telemetry:{host_id}` с TTL.
4. **GeoIP** — `hosts.country_code` заполняется по IP из карточки хоста (create/update/list) и при подключении агента.
5. **Host billing** — опциональные `billing_*` поля; daily APScheduler шлёт напоминания (email / Telegram / inbox) и auto-renew при online агенте. FX через Frankfurter. Telegram-бот: отдельный репо `vortex-telegram-bot`.
4. Секреты агентов и API keys — bcrypt hash; plaintext один раз при создании.

## Тесты

```bash
pytest                 # unit + OpenAPI smoke
RUN_INTEGRATION=1 pytest tests/test_integration.py
```

## Конфигурация

См. `.env.example` (`DATABASE_URL`, `REDIS_URL`, `JWT_SECRET_KEY`, CORS, rate limits, TTL).
