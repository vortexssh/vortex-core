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
    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.core.redis import get_redis_client
    from app.models.user import User

    email = "integ@example.com"
    password = "password123"

    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    if reg.status_code == 409:
        # already exists — ensure verification email can be re-sent
        resend = await client.post(
            "/api/v1/auth/resend-verification",
            json={"email": email},
        )
        assert resend.status_code == 200, resend.text
    else:
        assert reg.status_code == 201, reg.text
        assert "email" in reg.json()

    blocked = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    # Fresh signup must confirm email first; prior verified accounts may login.
    if blocked.status_code == 403:
        assert blocked.json()["error"]["code"] == "email_not_verified"
        async with AsyncSessionLocal() as session:
            user = (
                await session.execute(select(User).where(User.email == email.lower()))
            ).scalar_one()
            user_id = user.id
        redis = get_redis_client()
        verify_token = await redis.get(f"email_verify:user:{user_id}")
        assert verify_token, "verification token missing in Redis"
        verified = await client.post(
            "/api/v1/auth/verify-email",
            json={"token": verify_token},
        )
        assert verified.status_code == 200, verified.text
        token = verified.json()["access_token"]
    else:
        assert blocked.status_code == 200, blocked.text
        token = blocked.json()["access_token"]

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
