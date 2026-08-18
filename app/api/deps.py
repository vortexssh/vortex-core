from collections.abc import AsyncGenerator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.redis import get_redis
from app.core.security import decode_access_token, verify_secret
from app.core.twofa import totp_enforced
from app.models.user import User
from app.repositories.api_key import ApiKeyRepository
from app.repositories.user import UserRepository

bearer_scheme = HTTPBearer(auto_error=False)

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
RedisClient = Annotated[Redis, Depends(get_redis)]


async def get_current_user(
    session: DbSession,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> User:
    """Resolve user from JWT Bearer token or X-API-Key / Bearer API key."""
    users = UserRepository(session)

    if x_api_key:
        user = await _user_from_api_key(session, x_api_key)
        if user is not None:
            return user
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_api_key", "message": "Invalid API key"},
        )

    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "not_authenticated", "message": "Authentication required"},
        )

    token = credentials.credentials
    if token.startswith("vxk_"):
        user = await _user_from_api_key(session, token)
        if user is not None:
            return user
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_api_key", "message": "Invalid API key"},
        )

    try:
        payload = decode_access_token(token)
        user_id = UUID(payload["sub"])
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_token", "message": "Invalid or expired token"},
        ) from exc

    user = await users.get_by_id(user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_token", "message": "User not found or inactive"},
        )
    return user


async def _user_from_api_key(session: AsyncSession, raw_key: str) -> User | None:
    repo = ApiKeyRepository(session)
    users = UserRepository(session)
    prefix = raw_key[:12]
    candidates = await repo.find_by_prefix(prefix)
    for api_key in candidates:
        if repo.is_expired(api_key):
            continue
        if verify_secret(raw_key, api_key.key_hash):
            return await users.get_by_id(api_key.user_id)
    return None


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_2fa(user: CurrentUser) -> User:
    """Block agent-facing operations until TOTP is enabled (see SECURITY_LEVEL)."""
    if totp_enforced(user) and not user.is_2fa_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "2fa_required",
                "message": "Two-factor authentication must be enabled for this action",
            },
        )
    return user


UserWith2FA = Annotated[User, Depends(require_2fa)]

get_db = get_db_session

__all__ = [
    "CurrentUser",
    "DbSession",
    "RedisClient",
    "UserWith2FA",
    "get_current_user",
    "get_db",
    "get_redis",
    "require_2fa",
]
