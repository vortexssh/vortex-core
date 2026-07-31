#!/bin/sh
set -eu

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
