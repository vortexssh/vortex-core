import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    generate_totp_secret,
    hash_password,
    verify_password,
    verify_totp,
)
from app.main import create_app
from app.schemas.host import HostCreate


@pytest.fixture
def app():
    get_settings.cache_clear()
    return create_app()


@pytest.mark.asyncio
async def test_password_hash_roundtrip() -> None:
    hashed = hash_password("secret-password")
    assert verify_password("secret-password", hashed)
    assert not verify_password("wrong", hashed)


def test_totp_verify() -> None:
    secret = generate_totp_secret()
    import pyotp

    code = pyotp.TOTP(secret).now()
    assert verify_totp(secret, code)


def test_host_create_rejects_secrets() -> None:
    with pytest.raises(Exception):
        HostCreate(
            name="db",
            username="root",
            password="should-fail",  # type: ignore[call-arg]
        )


def test_jwt_roundtrip() -> None:
    from uuid import uuid4

    user_id = uuid4()
    token = create_access_token(subject=user_id)
    from app.core.security import decode_access_token

    payload = decode_access_token(token)
    assert payload["sub"] == str(user_id)


@pytest.mark.asyncio
async def test_openapi_contains_core_paths(app) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/auth/register" in paths
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/auth/verify-email" in paths
    assert "/api/v1/auth/resend-verification" in paths
    assert "/api/v1/hosts" in paths
    assert "/api/v1/tags" in paths
    assert "/api/v1/hosts/{host_id}/agents" in paths
    assert "/api/v1/hosts/{host_id}/tasks" in paths
    assert "/api/v1/hosts/{host_id}/telemetry" in paths
