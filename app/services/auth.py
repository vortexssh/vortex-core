import logging

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    build_totp_uri,
    create_access_token,
    generate_totp_secret,
    hash_password,
    verify_password,
    verify_totp,
)
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.auth import TokenResponse, TotpSetupResponse, UserCreate, UserLogin

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self._users = UserRepository(session)
        self._session = session

    async def register(self, payload: UserCreate) -> User:
        existing = await self._users.get_by_email(payload.email)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "email_taken", "message": "Email already registered"},
            )
        user = User(
            email=payload.email.lower(),
            password_hash=hash_password(payload.password),
        )
        user = await self._users.create(user)
        await self._session.commit()
        return user

    async def login(self, payload: UserLogin) -> TokenResponse:
        user = await self._users.get_by_email(payload.email)
        if user is None or not verify_password(payload.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "invalid_credentials", "message": "Invalid email or password"},
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "user_inactive", "message": "Account is inactive"},
            )
        if user.is_2fa_enabled:
            if not payload.totp_code or not user.totp_secret:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={
                        "code": "totp_required",
                        "message": "TOTP code required",
                    },
                )
            if not verify_totp(user.totp_secret, payload.totp_code):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={"code": "invalid_totp", "message": "Invalid TOTP code"},
                )
        token = create_access_token(subject=user.id)
        return TokenResponse(access_token=token)

    async def setup_2fa(self, user: User) -> TotpSetupResponse:
        if user.is_2fa_enabled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "2fa_already_enabled", "message": "2FA is already enabled"},
            )
        secret = generate_totp_secret()
        user.totp_secret = secret
        await self._users.save(user)
        await self._session.commit()
        return TotpSetupResponse(
            secret=secret,
            otpauth_uri=build_totp_uri(secret=secret, email=user.email),
        )

    async def verify_2fa(self, user: User, code: str) -> User:
        if not user.totp_secret:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "2fa_not_setup", "message": "Call /auth/2fa/setup first"},
            )
        if not verify_totp(user.totp_secret, code):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "invalid_totp", "message": "Invalid TOTP code"},
            )
        user.is_2fa_enabled = True
        await self._users.save(user)
        await self._session.commit()
        return user

    async def disable_2fa(self, user: User, code: str) -> User:
        if not user.is_2fa_enabled or not user.totp_secret:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "2fa_not_enabled", "message": "2FA is not enabled"},
            )
        if not verify_totp(user.totp_secret, code):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "invalid_totp", "message": "Invalid TOTP code"},
            )
        user.is_2fa_enabled = False
        user.totp_secret = None
        await self._users.save(user)
        await self._session.commit()
        return user

    async def update_profile(self, user: User, email: str | None) -> User:
        if email is not None:
            existing = await self._users.get_by_email(email)
            if existing is not None and existing.id != user.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"code": "email_taken", "message": "Email already registered"},
                )
            user.email = email.lower()
        await self._users.save(user)
        await self._session.commit()
        return user
