#!/bin/sh
set -eu

GEOIP_DB_PATH="${GEOIP_DB_PATH:-/app/data/GeoLite2-Country.mmdb}"
mkdir -p "$(dirname "$GEOIP_DB_PATH")"

if [ -n "${MAXMIND_LICENSE_KEY:-}" ] && [ ! -f "$GEOIP_DB_PATH" ]; then
  echo "Downloading GeoLite2-Country database..."
  tmp="$(mktemp -d)"
  if curl -fsSL \
    "https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-Country&license_key=${MAXMIND_LICENSE_KEY}&suffix=tar.gz" \
    | tar -xz -C "$tmp"; then
    found="$(find "$tmp" -name 'GeoLite2-Country.mmdb' -print -quit)"
    if [ -n "$found" ]; then
      mv "$found" "$GEOIP_DB_PATH"
      echo "GeoIP database installed at $GEOIP_DB_PATH"
    else
      echo "GeoLite2-Country.mmdb not found in archive" >&2
    fi
  else
    echo "GeoIP download failed — HTTP fallback will be used if enabled" >&2
  fi
  rm -rf "$tmp"
elif [ ! -f "$GEOIP_DB_PATH" ]; then
  echo "GeoIP database missing at $GEOIP_DB_PATH (set MAXMIND_LICENSE_KEY or mount a .mmdb file)"
fi

echo "Waiting for PostgreSQL..."
python - <<'PY'
import asyncio
import os
import sys

import asyncpg


async def wait() -> None:
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://", 1)
    for attempt in range(60):
        try:
            conn = await asyncpg.connect(url)
            await conn.close()
            print("PostgreSQL is ready")
            return
        except Exception as exc:  # noqa: BLE001
            print(f"  attempt {attempt + 1}/60: {exc}", flush=True)
            await asyncio.sleep(2)
    print("PostgreSQL did not become ready in time", file=sys.stderr)
    sys.exit(1)


asyncio.run(wait())
PY

echo "Running migrations..."
alembic upgrade head

echo "Starting Vortex Core..."
exec "$@"
