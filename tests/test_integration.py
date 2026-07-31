"""Integration tests — require PostgreSQL + Redis from docker-compose."""

from __future__ import annotations

import os

import pytest
import pyotp
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.redis import close_redis, init_redis
from app.main import create_app

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION") != "1",
    reason="Set RUN_INTEGRATION=1 with Postgres/Redis available",
)


@pytest.fixture
async def client():
    get_settings.cache_clear()
    application = create_app()
    await init_redis()
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await close_redis()


@pytest.mark.asyncio
async def test_auth_host_agent_2fa_flow(client: AsyncClient) -> None:
    email = "integ@example.com"
    password = "password123"

    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    if reg.status_code == 409:
        # already exists from previous run
        pass
    else:
        assert reg.status_code == 201, reg.text

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    setup = await client.post("/api/v1/auth/2fa/setup", headers=headers)
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    code = pyotp.TOTP(secret).now()
    verify = await client.post(
        "/api/v1/auth/2fa/verify",
        headers=headers,
        json={"code": code},
    )
    assert verify.status_code == 200
    assert verify.json()["is_2fa_enabled"] is True

    # Login again with TOTP
    login2 = await client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": password,
            "totp_code": pyotp.TOTP(secret).now(),
        },
    )
    assert login2.status_code == 200
    headers = {"Authorization": f"Bearer {login2.json()['access_token']}"}

    host = await client.post(
        "/api/v1/hosts",
        headers=headers,
        json={
            "name": "nat-box",
            "ip_address": None,
            "port": 22,
            "username": "ubuntu",
            "is_proxy_enabled": True,
        },
    )
    assert host.status_code == 201, host.text
    host_id = host.json()["id"]

    # Telemetry without agent data -> 404, but 2FA enforced (not 403)
    tel = await client.get(f"/api/v1/hosts/{host_id}/telemetry", headers=headers)
    assert tel.status_code == 404

    agent = await client.post(f"/api/v1/hosts/{host_id}/agents", headers=headers)
    assert agent.status_code == 201, agent.text
    assert agent.json()["secret"].startswith("vxa_")
