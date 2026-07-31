# Vortex Core — деплой на сервер

## Требования

- Linux VPS (Ubuntu 22.04+ / Debian 12+)
- Docker Engine + Compose plugin
- Nginx + Certbot
- Открыты порты **80** и **443**
- Домен с A/AAAA-записью на IP сервера (для HTTPS)

## 1. Подготовка сервера

```bash
curl -fsSL https://get.docker.com | sh
sudo apt-get update
sudo apt-get install -y nginx certbot python3-certbot-nginx
```

## 2. Код

```bash
sudo mkdir -p /opt/vortex-core
cd /opt/vortex-core
git clone <YOUR_REPO_URL> .
```

## 3. Конфиг

```bash
cp .env.production.example .env
nano .env
```

| Переменная | Что поставить |
|---|---|
| `POSTGRES_PASSWORD` | сильный пароль БД |
| `JWT_SECRET_KEY` | `openssl rand -hex 32` |
| `DOMAIN` | `api.vortex.timant32.ru` |
| `CORS_ORIGINS` | origin веб-панели |

## 4. Docker API

```bash
cd /opt/vortex-core
docker compose up -d --build
# API слушает только 127.0.0.1:8000
```

## 5. Nginx + TLS

```bash
sudo mkdir -p /var/www/certbot
sudo cp deploy/nginx-api.http.conf /etc/nginx/sites-available/api.vortex.timant32.ru
sudo ln -sf /etc/nginx/sites-available/api.vortex.timant32.ru /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

sudo certbot --nginx -d api.vortex.timant32.ru --non-interactive --agree-tos -m admin@timant32.ru --redirect
```

Проверка:

```bash
curl -fsS https://api.vortex.timant32.ru/api/v1/health
```

## 6. Обновление

```bash
cd /opt/vortex-core
git pull
docker compose up -d --build
```

## Архитектура

```
Internet → Nginx (:80/:443) → 127.0.0.1:8000 (api container)
                               ├─ postgres
                               └─ redis
```
