import logging
import re
import secrets
from uuid import UUID

from fastapi import HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
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
from app.schemas.auth import (
    RegisterResponse,
    TokenResponse,
    TotpSetupResponse,
    UserCreate,
    UserLogin,
    UserUpdate,
)
from app.services.email import send_verification_email

logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
_TOKEN_KEY = "email_verify:token:{token}"
_USER_TOKEN_KEY = "email_verify:user:{user_id}"


class AuthService:
    def __init__(self, session: AsyncSession, redis: Redis | None = None) -> None:
        self._users = UserRepository(session)
        self._session = session
        self._redis = redis

    def _require_redis(self) -> Redis:
        if self._redis is None:
            raise RuntimeError("Redis is required for email verification")
        return self._redis

    async def register(self, payload: UserCreate) -> RegisterResponse:
        existing = await self._users.get_by_email(payload.email)
        if existing is not None:
            if not existing.is_email_verified:
                await self._issue_and_send_verification(existing)
                return RegisterResponse(
                    email=existing.email,
                    message="Account pending verification — we re-sent the confirmation email",
                )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "email_taken", "message": "Email already registered"},
            )
        user = User(
            email=payload.email.lower(),
            password_hash=hash_password(payload.password),
            is_email_verified=False,
        )
        user = await self._users.create(user)
        await self._session.commit()
        await self._issue_and_send_verification(user)
        return RegisterResponse(email=user.email)

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
        if not user.is_email_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "email_not_verified",
                    "message": "Confirm your email before signing in",
                },
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

    async def verify_email(self, token: str) -> TokenResponse:
        redis = self._require_redis()
        key = _TOKEN_KEY.format(token=token)
        user_id_raw = await redis.get(key)
        if not user_id_raw:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "invalid_verification_token",
                    "message": "Verification link is invalid or expired",
                },
            )
        try:
            user_id = UUID(str(user_id_raw))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "invalid_verification_token",
                    "message": "Verification link is invalid or expired",
                },
            ) from exc

        user = await self._users.get_by_id(user_id)
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "invalid_verification_token",
                    "message": "Verification link is invalid or expired",
                },
            )

        user.is_email_verified = True
        await self._users.save(user)
        await self._session.commit()
        await self._clear_verification_tokens(user.id, token)

        return TokenResponse(access_token=create_access_token(subject=user.id))

    async def resend_verification(self, email: str) -> RegisterResponse:
        user = await self._users.get_by_email(email)
        # Always return the same shape to avoid email enumeration
        generic = RegisterResponse(
            email=email.lower(),
            message="If that address needs verification, a new email was sent",
        )
        if user is None or user.is_email_verified or not user.is_active:
            return generic
        await self._issue_and_send_verification(user)
        return generic

    async def _issue_and_send_verification(self, user: User) -> None:
        redis = self._require_redis()
        settings = get_settings()
        await self._clear_verification_tokens(user.id)

        token = secrets.token_urlsafe(32)
        ttl = settings.email_verification_ttl_hours * 3600
        await redis.set(_TOKEN_KEY.format(token=token), str(user.id), ex=ttl)
        await redis.set(_USER_TOKEN_KEY.format(user_id=user.id), token, ex=ttl)

        base = settings.web_app_url.rstrip("/")
        verify_url = f"{base}/verify-email?token={token}"

        try:
            await send_verification_email(to_email=user.email, verify_url=verify_url)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "code": "email_send_failed",
                    "message": "Could not send verification email — try again later",
                },
            ) from exc

    async def _clear_verification_tokens(
        self,
        user_id: UUID,
        known_token: str | None = None,
    ) -> None:
        redis = self._require_redis()
        user_key = _USER_TOKEN_KEY.format(user_id=user_id)
        token = known_token or await redis.get(user_key)
        if token:
            await redis.delete(_TOKEN_KEY.format(token=token))
        await redis.delete(user_key)

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

    async def update_profile(self, user: User, payload: UserUpdate) -> User:
        data = payload.model_dump(exclude_unset=True)

        if "email" in data and data["email"] is not None:
            email = str(data["email"]).lower()
            existing = await self._users.get_by_email(email)
            if existing is not None and existing.id != user.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"code": "email_taken", "message": "Email already registered"},
                )
            if email != user.email:
                user.email = email
                user.is_email_verified = False

        if "public_slug" in data:
            user.public_slug = _normalize_public_slug(data["public_slug"])
            if user.public_slug is not None:
                taken = await self._users.get_by_public_slug(user.public_slug)
                if taken is not None and taken.id != user.id:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={
                            "code": "slug_taken",
                            "message": "Public slug already in use",
                        },
                    )

        await self._users.save(user)
        await self._session.commit()

        if "email" in data and not user.is_email_verified:
            await self._issue_and_send_verification(user)

        return user

    async def change_password(
        self,
        user: User,
        *,
        current_password: str,
        new_password: str,
    ) -> None:
        if not verify_password(current_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "invalid_password",
                    "message": "Current password is incorrect",
                },
            )
        if len(new_password) < 8:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "weak_password",
                    "message": "New password must be at least 8 characters",
                },
            )
        if current_password == new_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "password_unchanged",
                    "message": "New password must differ from the current one",
                },
            )
        user.password_hash = hash_password(new_password)
        await self._users.save(user)
        await self._session.commit()


def _normalize_public_slug(value: str | None) -> str | None:
    if value is None:
        return None
    slug = value.strip().lower()
    if slug == "":
        return None
    if not _SLUG_RE.match(slug):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "invalid_slug",
                "message": "Slug must be 2–63 chars: lowercase letters, digits, hyphens",
            },
        )
    return slug
