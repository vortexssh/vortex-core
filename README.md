# Vortex Core

Бэкенд экосистемы **VortexSSH**: облачная записная книжка метаданных хостов и транзитный WebSocket Tunnel Router для обхода NAT / Web-терминала.

Клиенты (GUI/TUI) и хост-агенты (Go) работают через этот сервис. Сам Core **никогда** не хранит пароли целевых серверов и приватные SSH-ключи пользователей — только метаданные.

## Возможности

| Функция | Описание |
|---|---|
| **REST API** | Метаданные хостов, профили пользователей, жёсткая 2FA (TOTP) |
| **WebSocket Tunnel Router** | Долгоживущие соединения с агентами, прокси TCP/SSH, PTY для WebSSH |
| **Телеметрия** | CPU/RAM и т.п. пишутся **только в Redis** (с TTL), не в PostgreSQL |

> Сейчас в репозитории — каркас: конфиг, async PostgreSQL, модели `users` / `hosts`, health-check. Auth, CRUD, агенты и туннели — следующие итерации.

## Стек

- Python 3.11+
- FastAPI (async)
- PostgreSQL + SQLAlchemy 2.0 / SQLModel + asyncpg
- Redis (redis-py async)
- Alembic
- JWT + TOTP (Google Authenticator)

## Архитектура

Слоистая структура:

```
Routers → Services → Repositories → Models
```

```
app/
├── main.py              # FastAPI app + lifespan
├── core/                # Settings, DB engine
├── models/              # ORM (users, hosts, …)
├── schemas/             # Pydantic DTO
├── repositories/        # Доступ к данным
├── services/            # Бизнес-логика
├── api/                 # REST-роутеры + Depends
└── websocket/           # Tunnel Router
```

## Требования

- Python 3.11+
- PostgreSQL 14+
- Redis 6+

## Быстрый старт

```bash
# 1. Клон и venv
cd VortexCore
python3 -m venv .venv
source .venv/bin/activate

# 2. Зависимости
pip install -r requirements.txt

# 3. Конфиг
cp .env.example .env
# отредактируйте DATABASE_URL, REDIS_URL, JWT_SECRET_KEY

# 4. Запуск
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Проверка:

- Health: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health) → `{"status":"ok"}`
- OpenAPI: [http://localhost:8000/docs](http://localhost:8000/docs)

## Конфигурация

Переменные окружения (см. `.env.example`):

| Переменная | Описание |
|---|---|
| `APP_NAME` | Имя приложения |
| `APP_ENV` | `development` / `production` |
| `DEBUG` | SQL echo и debug FastAPI |
| `API_V1_PREFIX` | Префикс API (`/api/v1`) |
| `DATABASE_URL` | DSN async PostgreSQL (`postgresql+asyncpg://…`) |
| `REDIS_URL` | URL Redis |
| `JWT_SECRET_KEY` | Секрет JWT (**≥ 32 символов**) |
| `JWT_ALGORITHM` | Алгоритм JWT (по умолчанию `HS256`) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | TTL access-токена |
| `TELEMETRY_TTL_SECONDS` | TTL ключей телеметрии в Redis |

## Модели (PostgreSQL)

### `users`

| Поле | Назначение |
|---|---|
| `email` | Уникальный логин |
| `password_hash` | Хэш пароля аккаунта Vortex (не SSH) |
| `totp_secret` | Секрет TOTP |
| `is_2fa_enabled` | Флаг обязательной 2FA |

### `hosts`

Только метаданные (zero-trust):

| Поле | Назначение |
|---|---|
| `name` | Отображаемое имя |
| `ip_address` | IP (`INET`) |
| `port` | SSH-порт |
| `username` | Имя пользователя на хосте |
| `is_proxy_enabled` | Туннель через агента |

Планируемые сущности: `api_keys`, `tags` / `host_tags`, `agents`, `tasks` / `task_logs`.

## Правила безопасности

1. **Zero-trust** — Core не принимает и не хранит пароли/приватные ключи целевых серверов.
2. **2FA enforcement** — эндпоинты, связанные с агентами (телеметрия, WebSSH, задачи), требуют `is_2fa_enabled == True`.
3. **No DB metrics** — телеметрия агентов только в Redis с TTL.

## Разработка

```bash
# Импорт приложения / проверка настроек
python -c "from app.main import app; print(app.title)"
```

Dependency injection: сессия БД через `Depends(get_db)` из `app.api.deps`.

## Лицензия

Проприетарный код проекта VortexSSH. Все права защищены.
