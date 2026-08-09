# Руководство для авторов демонов (Vortex Plugins)

Документ для тех, кто пишет **out-of-process плагины** Vortex: манифест, declarative UI, daemon, state и RPC.

Краткая спецификация контракта: [`../PLUGIN_SPEC.md`](../PLUGIN_SPEC.md).  
Эталонный плагин: [`../examples/fake-metrics-plugin/`](../examples/fake-metrics-plugin/).

`api_version`: **1**.

---

## 1. Зачем демоны

Vortex Core и Web — общий продукт. Уникальные интеграции (мониторинг мощности, CMDB, внешние алерты, опрос произвольного API) не должны попадать в основной код.

**Демон** — ваш процесс (Python, Go, Node, …), который:

1. Живёт у пользователя (дом, VPS, рядом с Home Assistant / MQTT / чем угодно).
2. Сам ходит во внешние системы и хранит их секреты.
3. Подключается к Core **outbound** (как host-агент) — работает за NAT.
4. Публикует live-данные в Core и отвечает на RPC из Web UI.
5. Описывает UI декларативно в манифесте — без React в вашем пакете.

```text
[Ваш API / железо] → [Daemon] ──WSS/HTTPS──→ [Vortex Core] ←──REST── [Vortex Web]
                              state + RPC         Redis state
                                                  PG: install/bindings/manifest
```

---

## 2. Что можно и чего нельзя

### Можно

- Новые страницы, пункты сайдбара, вкладки Settings.
- Колонки и expand-панели у хостов.
- Формы, таблицы, метрики, графики (в рамках DSL).
- Свои методы API через **RPC** (Core проксирует вызов на ваш WS).
- Per-install и per-host конфиг (JSON Schema).
- Live state с TTL в Redis.

### Нельзя (by design)

- Выполнять произвольный код внутри Core или Web.
- Читать SSH-пароли / приватные ключи пользователей (zero-trust).
- Писать **live**-телеметрию плагина в PostgreSQL (live → только Redis).
- Видеть installs других пользователей.
- Обходить JWT / 2FA пользователя на user-facing API.

**Исключение для истории:** дневные агрегаты (`POST …/daemon/metrics/daily`) пишутся в PostgreSQL (`plugin_daily_metrics`) — для календарей и публичных страниц без онлайн-демона. Live state по-прежнему только Redis.

Секреты интеграций (токены HA, MQTT, API keys третьих сторон) остаются **только на машине демона**.

---

## 3. Роли и идентификаторы

| Сущность | Кто выдаёт | Формат | Где используется |
|----------|------------|--------|------------------|
| `plugin_id` | вы | `com.example.my_plugin` | поле `id` в манифесте; уникален на пользователя |
| `install_id` | Core | UUID | URL API/WS после установки |
| `daemon_token` | Core | `vxp_…` | один раз при install / rotate; auth демона |
| `host_id` | Core | UUID | привязка state/RPC к хосту |

Пользователь авторизуется JWT / `vxk_…`. Демон — **только** `vxp_…` (не user JWT).

---

## 4. Структура пакета

```text
my-plugin/
  vortex-plugin.json      # обязателен
  ui/                     # declarative views (опционально как файлы)
    pages/
    panels/
  schemas/                # JSON Schema
  README.md
  daemon/                 # ваш рантайм (любой язык)
```

При установке через Web/API Core принимает **один JSON-манифест**. Пути вроде `"view": "ui/pages/home.json"` должны быть **заинлайнены** в `manifest.views` (и схемы — в `manifest.schemas`), либо клиент должен подставить файлы до `POST`.

Рекомендация: либо self-contained `vortex-plugin.json` с inline `views`/`schemas`, либо **ZIP-пакет** (`vortex-plugin.json` + `ui/` + `schemas/`) → Web Settings → Plugins → upload `.zip`, либо `POST /api/v1/plugins/install-package`.

---

## 5. Манифест (`vortex-plugin.json`)

### Обязательные поля

```json
{
  "id": "com.example.my_plugin",
  "name": "My Plugin",
  "version": "1.0.0",
  "api_version": 1,
  "permissions": ["state.write", "rpc", "nav", "pages"]
}
```

| Поле | Правила |
|------|---------|
| `id` | `^[a-z0-9][a-z0-9._-]*$`, 3–128 символов, reverse-DNS |
| `name` | отображаемое имя, ≤128 |
| `version` | строка ≤32 (semver рекомендуется) |
| `api_version` | строго `1` |
| `permissions` | только из белого списка (см. ниже) |

### Опциональные поля

| Поле | Назначение |
|------|------------|
| `config_schema` | schema install-level конфига (object или ключ в `schemas`) |
| `host_binding_schema` | schema per-host binding |
| `rpc` | объявленные методы `[{ "method": "refresh", "input": "...", "output": "..." }]` |
| `ui.contributions` | слоты UI |
| `views` | map `path →` дерево DSL |
| `schemas` | map `path →` JSON Schema object |

Неизвестные `permissions` / `slot` → установка отклоняется (422).

---

## 6. Permissions и слоты

Каждый UI-слот требует permission. Нет permission → contribution **молча отбрасывается** из `ui-bundle`.

| Permission | Открывает слоты / возможности |
|------------|-------------------------------|
| `state.write` | `POST …/daemon/state` |
| `rpc` | `POST …/rpc/{method}` + обработчик на WS |
| `host.bind` | `PUT/DELETE …/bindings/{host_id}` |
| `nav` | `nav.items` |
| `pages` | `routes` |
| `hosts.columns` | `hosts.table.columns` |
| `hosts.panels` | `hosts.detail.panels` |
| `hosts.actions` | `hosts.row.actions`, `host.actions` |
| `hosts.editor` | `hosts.editor.fields` |
| `settings` | `settings.tabs` |

Берите минимальный набор. Пример «метрика на хосте + страница + RPC»:

```json
"permissions": [
  "host.bind",
  "state.write",
  "rpc",
  "nav",
  "pages",
  "hosts.columns",
  "hosts.panels",
  "settings"
]
```

---

## 7. UI contributions (слоты)

### `nav.items`

```json
{
  "slot": "nav.items",
  "id": "main-nav",
  "item": {
    "label": "My Plugin",
    "icon": "activity",
    "route": "plugin:com.example.my_plugin/home"
  }
}
```

`route` вида `plugin:{plugin_id}/{path}` → URL Web `/plugins/{plugin_id}/{path}`.

### `routes`

```json
{
  "slot": "routes",
  "id": "home",
  "route": "plugin:com.example.my_plugin/home",
  "view": "ui/pages/home.json"
}
```

`view` — ключ в `manifest.views` или inline-объект DSL.

### `hosts.table.columns`

```json
{
  "slot": "hosts.table.columns",
  "id": "power-col",
  "column": {
    "header": "Power",
    "bind": "plugin.state.power_w",
    "component": "metric",
    "unit": "W"
  }
}
```

Значение читается из **per-host** state (`GET …/state?host_id=`).

### `hosts.detail.panels`

```json
{
  "slot": "hosts.detail.panels",
  "id": "power-panel",
  "view": "ui/panels/host.json",
  "requires_host_binding": true
}
```

Рендерится в expand строки хоста. При `requires_host_binding: true` UI может скрывать панель без binding (зависит от клиента; в v1 Web показывает панель всегда, binding — для вашей логики).

### `settings.tabs`

```json
{
  "slot": "settings.tabs",
  "id": "settings",
  "label": "My Plugin",
  "view": "ui/pages/settings.json"
}
```

### `hosts.editor.fields` / actions

- `hosts.editor.fields` — JSON Schema (`schema` / inline) для полей привязки в редакторе хоста.
- `hosts.row.actions` / `host.actions` — действия с RPC (`action` / payload).

`id` contribution уникален в рамках плагина (строка ≤64).

---

## 8. Declarative UI DSL

Дерево узлов с полем `type`. Неизвестный `type` → «Unsupported widget», UI не падает.

### Layout

| type | Поля | Описание |
|------|------|----------|
| `stack` | `title?`, `children[]` | вертикальный стек |
| `grid` | `columns?` (число), `children[]` | сетка |
| `tabs` | `children[]` | вкладки (v1: простой стек) |
| `panel` | `title?`, `children[]` | карточка с рамкой |

### Display

| type | Поля | Описание |
|------|------|----------|
| `text` / `markdown` | `text?`, `bind?` | текст; markdown в v1 как plain text |
| `metric` | `label?`, `bind`, `unit?` | крупное число |
| `badge` | `bind`, `tone?` (`neon`/`warn`) | бейдж |
| `progress` | `label?`, `bind` | 0–100 |
| `sparkline` / `chart` | `label?`, `bind` | массив чисел или `{value}` |
| `table` | `bind`, `columns[{key,header}]` | таблица по массиву объектов |

### Input / actions

| type | Поля | Описание |
|------|------|----------|
| `button` | `label`, `action`, `enableIf?` | RPC `action` |
| `confirm` | как button + `confirmMessage` | confirm → RPC |
| `form` | `schema`, `submitAction`, `submitLabel?` | поля из JSON Schema → RPC params |
| `repeater` | `bind`, `item` | повтор `item` по массиву; элемент в `plugin.state.item` |

### Условия

- `visibleIf`: скрыть узел, если выражение ложно.
- `enableIf`: для button — disable.

Выражения:

- путь: `plugin.state.online` (truthy);
- сравнение: `plugin.state.online == true`, `plugin.state.mode == "auto"`.

Без `eval`, без HTML.

### Bindings (контекст)

| Префикс | Источник |
|---------|----------|
| `host.*` | метаданные хоста Core (без секретов) |
| `install.config` / `install.config.*` | конфиг install |
| `binding.config` / `binding.config.*` | per-host binding |
| `plugin.state` / `plugin.state.*` | Redis state (global или host, в зависимости от страницы) |
| `action.result` / `action.result.*` | результат последнего RPC в этом view |

Пример страницы:

```json
{
  "type": "stack",
  "children": [
    { "type": "text", "text": "Power monitor" },
    { "type": "metric", "label": "Watts", "bind": "plugin.state.power_w", "unit": "W" },
    { "type": "sparkline", "label": "History", "bind": "plugin.state.history" },
    { "type": "button", "label": "Refresh", "action": "refresh" },
    {
      "type": "form",
      "submitAction": "configure",
      "submitLabel": "Save",
      "schema": {
        "type": "object",
        "properties": {
          "entity_id": { "type": "string", "title": "Entity ID" }
        }
      }
    }
  ]
}
```

---

## 9. Установка плагина

### Через Web

1. Settings → **Plugins**.
2. Загрузить ZIP с `vortex-plugin.json` (+ `ui/`, `schemas/`) → Install (или JSON sample).
3. **Сразу скопировать** `daemon_token` (`vxp_…`) — повторно не показывается.
4. Сохранить `install_id` (UUID из списка installs).

### Через API

```http
POST /api/v1/plugins
Authorization: Bearer <jwt|vxk_…>
Content-Type: application/json

{
  "manifest": { /* полный vortex-plugin.json */ },
  "config": { "interval_seconds": 10 }
}
```

Ответ `201`:

```json
{
  "id": "<install_id>",
  "plugin_id": "com.example.my_plugin",
  "daemon_token": "vxp_…",
  "status": "active",
  ...
}
```

Повторная установка того же `plugin_id` у пользователя → `409 plugin_already_installed`.  
Обновление манифеста: `PATCH /api/v1/plugins/{install_id}` с новым `manifest`.  
Ротация токена: `POST /api/v1/plugins/{install_id}/rotate-token`.

### Host binding

```http
PUT /api/v1/plugins/{install_id}/bindings/{host_id}
Authorization: Bearer …

{ "config": { "entity_id": "sensor.server_power" } }
```

Нужен permission `host.bind`. Config валидируется по `host_binding_schema` (subset: `required`, `additionalProperties: false`).

---

## 10. Контракт демона

Демону нужны три вещи:

```bash
export VORTEX_CORE_URL=https://api.example.com   # без trailing slash
export VORTEX_INSTALL_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
export VORTEX_DAEMON_TOKEN=vxp_…
```

### 10.1. WebSocket presence + RPC

```text
WSS {core}/ws/plugin/{install_id}?token={vxp_…}
```

`http` → `ws`, `https` → `wss`.

После accept Core шлёт:

```json
{ "type": "connected", "install_id": "…" }
```

**Core → Daemon**

```json
{
  "type": "rpc_request",
  "request_id": "uuid",
  "method": "refresh",
  "params": {},
  "host_id": "optional-uuid"
}
```

**Daemon → Core**

```json
{
  "type": "rpc_response",
  "request_id": "uuid",
  "result": { "ok": true, "power_w": 42 }
}
```

или

```json
{
  "type": "rpc_response",
  "request_id": "uuid",
  "error": "entity not found"
}
```

Опционально:

```json
{ "type": "heartbeat" }
```

Правила RPC:

1. Метод **должен** быть объявлен в `manifest.rpc`.
2. Нужен permission `rpc`.
3. Timeout на стороне Core ~15s → пользователю `504 rpc_failed` / offline `503 daemon_offline`.
4. Пока WS offline, UI RPC недоступен — state push по HTTPS всё ещё можно (если демон жив, но WS упал — лучше держать оба канала).

Рекомендуемый цикл демона:

1. Connect WS (reconnect с backoff).
2. Параллельно: периодический `POST` state.
3. На каждый `rpc_request` — обработать и ответить тем же `request_id`.
4. После RPC часто имеет смысл сразу запушить обновлённый state.

### 10.1b. Bindings list (daemon)

```http
GET /api/v1/plugins/{install_id}/daemon/bindings
X-Plugin-Token: vxp_…
```

Ответ: `[{ "host_id": "…", "config": { "entity_id": "sensor.…" } }, …]`.  
Используйте это вместо дублирования mapping в локальном файле.

### 10.1c. Daily metrics upsert (PostgreSQL)

```http
POST /api/v1/plugins/{install_id}/daemon/metrics/daily
X-Plugin-Token: vxp_…
Content-Type: application/json

{
  "samples": [
    {
      "host_id": "<uuid>",
      "metric": "energy_kwh",
      "day": "2026-08-10",
      "value": 1.234
    }
  ]
}
```

Upsert по `(install_id, host_id, metric, day)`. Нужен permission `state.write`.  
Пользователь читает: `GET …/metrics/daily?from=YYYY-MM-DD&to=YYYY-MM-DD&host_id=&metric=energy_kwh`.

### 10.2. State push (HTTPS)

```http
POST /api/v1/plugins/{install_id}/daemon/state
X-Plugin-Token: vxp_…
Content-Type: application/json

{
  "state": { "power_w": 120.5, "online": true },
  "host_id": null,
  "history_key": "power_w"
}
```

| Поле | Описание |
|------|----------|
| `state` | произвольный JSON-object (то, что читает UI через `plugin.state.*`) |
| `host_id` | если задан — пишется в per-host ключ; хост должен принадлежать владельцу install |
| `history_key` | опционально: LPUSH в history-list для графиков |

**Redis (TTL по умолчанию):**

| Ключ | TTL (default) |
|------|----------------|
| `plugin:{install_id}:state` | 300s (`plugin_state_ttl_seconds`) |
| `plugin:{install_id}:host:{host_id}:state` | 300s |
| history lists | size 120, TTL 7200s |

Если пушить реже TTL — UI увидит пустой state. Либо пушьте чаще TTL, либо учитывайте stale UI.

**Глобальный vs host state**

- Страница плагина / settings → обычно **global** state (`host_id` не передаёте).
- Колонка/панель хоста → **host** state (`host_id` = UUID хоста).
- Типичный паттерн: демон знает map `host_id → external entity` из bindings (bindings демон может получить только если вы их передали в config или храните у себя; Core не стримит bindings на WS автоматически в v1 — храните mapping в конфиге демона или запрашивайте через свой канал).

> В v1 демон **не** получает список bindings по WS. Практичный путь: пользователь задаёт mapping в install `config` / файле демона, либо вы добавляете RPC `list_bindings` на своей стороне после того, как пользователь сохранил binding в Web (и передал демону через ваш `config`).

### 10.3. Минимальный псевдокод

```python
# connect WS, on message:
if msg["type"] == "rpc_request":
    try:
        result = handle(msg["method"], msg.get("params") or {}, msg.get("host_id"))
        ws.send({"type": "rpc_response", "request_id": msg["request_id"], "result": result})
    except Exception as e:
        ws.send({"type": "rpc_response", "request_id": msg["request_id"], "error": str(e)})

# every N seconds:
http.post(
  f"{CORE}/api/v1/plugins/{INSTALL}/daemon/state",
  headers={"X-Plugin-Token": TOKEN},
  json={"state": snapshot(), "host_id": host_id_or_null, "history_key": "power_w"},
)
```

Готовые хелперы: [`examples/fake-metrics-plugin/vortex_plugin_sdk.py`](../examples/fake-metrics-plugin/vortex_plugin_sdk.py).

---

## 11. User-facing API (для отладки, не для демона)

Эти вызовы делает Web / пользовательский клиент:

| Method | Path | Заметка |
|--------|------|---------|
| GET | `/plugins/ui-bundle` | все contributions активных installs |
| GET | `/plugins/{id}/state?host_id=` | чтение Redis state |
| POST | `/plugins/{id}/rpc/{method}` | `{ "params": {}, "host_id": null }` → WS RPC |
| GET | `/plugins/{id}/manifest` | сырой манифест |

Демон **не** должен использовать user JWT для state write — только `X-Plugin-Token`.

---

## 12. Пошаговый туториал (от нуля до колонки на Hosts)

1. **Спроектируйте данные**  
   Что показываем? Например `{ "power_w": number, "online": bool }`.

2. **Напишите манифест** с permissions, `rpc`, contributions, inline `views`.

3. **Установите** через Settings → Plugins, сохраните `install_id` + `vxp_…`.

4. **Запустите демон** с env (см. Fake Metrics README).

5. **Проверьте**  
   - в списке plugins: `daemon online`;  
   - сайдбар: ваш nav item;  
   - страница `/plugins/.../home`: метрика обновляется;  
   - кнопка Refresh/Bump вызывает RPC;  
   - для host column: пушьте state с `host_id`.

6. **Упакуйте** репозиторий: манифест + daemon + README с env-переменными.

---

## 13. Рекомендации по дизайну плагина

1. **Идемпотентный state** — каждый push полный снимок нужных полей, не «дельта», если UI биндится на плоские ключи.
2. **Стабильные ключи** в `plugin.state` (`power_w`, не меняйте имена без bump version).
3. **Версионируйте** `version` манифеста и совместимость state.
4. **Мало RPC, много push** — UI должен быть отзывчивым от polling state; RPC — для действий.
5. **Не кладите секреты** во `state` / `config`, которые уходят в Web — config install виден владельцу аккаунта через API.
6. **Rate limits** — не долбите state чаще раза в 1–5s на хост без нужды; connect rate limit ~60/min с IP.
7. **Reconnect** — экспоненциальный backoff на WS; при `4000 Replaced` значит второй инстанс демона с тем же install — оставьте один.
8. **Один install — один демон** (активный WS). Второй вытеснит первый.

---

## 14. Безопасность чеклист

- [ ] Токен `vxp_…` только в env/secret store демона, не в git.
- [ ] После rotate старый токен мёртв — обновите деплой.
- [ ] Внешние API keys только на демоне.
- [ ] В `state` нет PII/секретов сверх необходимого для UI.
- [ ] Permissions минимальны.
- [ ] Манифест не обещает слоты без permission.
- [ ] RPC methods все перечислены в `manifest.rpc`.

---

## 15. Troubleshooting

| Симптом | Причина / что проверить |
|---------|-------------------------|
| Install 422 `invalid_manifest` | `api_version`, id pattern, unknown permission/slot |
| Install 409 | плагин с таким `id` уже есть у пользователя |
| Daemon connect сразу closes | неверный token / install disabled / rate limit |
| UI: daemon offline | WS не подключён; смотри firewall egress 443 |
| State всегда `—` | не пушите / TTL истёк / пушите global, а колонка ждёт host state |
| RPC 503 `daemon_offline` | нет активного WS |
| RPC 404 `rpc_method_not_found` | метод не в `manifest.rpc` |
| Contribution не в UI | нет permission для слота / install `status=disabled` |
| Nav есть, страница empty | нет matching `routes` contribution или `view` не заинлайнен в `views` |

Логи Core: ошибки WS plugin (`Plugin websocket error`).  
Локально: гоняйте Fake Metrics до своих интеграций — так отделяете проблемы платформы от вашей логики.

---

## 16. Совместимость

- Ломающие изменения контракта → новый `api_version`.
- Новые виджеты DSL могут появляться аддитивно; старые клиенты показывают «Unsupported widget».
- Неизвестные поля в манифесте: зависит от валидатора; не полагайтесь на игнор — держитесь спеки v1.
- Reference: всегда сверяйтесь с [`PLUGIN_SPEC.md`](../PLUGIN_SPEC.md) и кодом `app/schemas/plugin.py`.

---

## 17. Ссылки

| Ресурс | Путь |
|--------|------|
| Спека v1 | [`PLUGIN_SPEC.md`](../PLUGIN_SPEC.md) |
| Fake Metrics | [`examples/fake-metrics-plugin/`](../examples/fake-metrics-plugin/) |
| HA Power (local) | [`../../vortex-plugin-ha-power/`](../../vortex-plugin-ha-power/) |
| SDK helpers | [`examples/fake-metrics-plugin/vortex_plugin_sdk.py`](../examples/fake-metrics-plugin/vortex_plugin_sdk.py) |
| Core router | `app/api/v1/plugins.py` |
| WS handler | `app/websocket/routes.py` (`/ws/plugin/...`) |
| Web renderer | VortexWeb `src/plugins/` |

Если не хватает слота или виджета для вашего кейса — это расширение платформы (`api_version` / Core+Web), а не хак внутри демона. Демон остаётся тонким адаптером к внешнему миру.
