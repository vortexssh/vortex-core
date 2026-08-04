from fastapi import APIRouter, Request, status

from app.api.deps import CurrentUser, DbSession, RedisClient
from app.core.config import get_settings
from app.core.rate_limit import client_ip, rate_limiter
from app.schemas.auth import (
    EmailVerifyRequest,
    PasswordChangeRequest,
    RegisterResponse,
    ResendVerificationRequest,
    TokenResponse,
    TotpDisableRequest,
    TotpSetupResponse,
    TotpVerifyRequest,
    UserCreate,
    UserLogin,
    UserRead,
)
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: UserCreate,
    session: DbSession,
    redis: RedisClient,
    request: Request,
) -> RegisterResponse:
    settings = get_settings()
    rate_limiter.check(
        f"register:{client_ip(request)}",
        limit=settings.login_rate_limit_per_minute,
    )
    service = AuthService(session, redis)
    return await service.register(payload)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: UserLogin,
    session: DbSession,
    request: Request,
) -> TokenResponse:
    settings = get_settings()
    rate_limiter.check(
        f"login:{client_ip(request)}",
        limit=settings.login_rate_limit_per_minute,
    )
    service = AuthService(session)
    return await service.login(payload)


@router.post("/verify-email", response_model=TokenResponse)
async def verify_email(
    payload: EmailVerifyRequest,
    session: DbSession,
    redis: RedisClient,
) -> TokenResponse:
    service = AuthService(session, redis)
    return await service.verify_email(payload.token)


@router.post("/resend-verification", response_model=RegisterResponse)
async def resend_verification(
    payload: ResendVerificationRequest,
    session: DbSession,
    redis: RedisClient,
    request: Request,
) -> RegisterResponse:
    settings = get_settings()
    rate_limiter.check(
        f"resend-verify:{client_ip(request)}",
        limit=settings.login_rate_limit_per_minute,
    )
    service = AuthService(session, redis)
    return await service.resend_verification(payload.email)


@router.post("/2fa/setup", response_model=TotpSetupResponse)
async def setup_2fa(user: CurrentUser, session: DbSession) -> TotpSetupResponse:
    service = AuthService(session)
    from app.repositories.user import UserRepository

    db_user = await UserRepository(session).get_by_id(user.id)
    assert db_user is not None
    return await service.setup_2fa(db_user)


@router.post("/2fa/verify", response_model=UserRead)
async def verify_2fa(
    payload: TotpVerifyRequest,
    user: CurrentUser,
    session: DbSession,
) -> UserRead:
    from app.repositories.user import UserRepository

    service = AuthService(session)
    db_user = await UserRepository(session).get_by_id(user.id)
    assert db_user is not None
    updated = await service.verify_2fa(db_user, payload.code)
    return UserRead.model_validate(updated)


@router.post("/2fa/disable", response_model=UserRead)
async def disable_2fa(
    payload: TotpDisableRequest,
    user: CurrentUser,
    session: DbSession,
) -> UserRead:
    from app.repositories.user import UserRepository

    service = AuthService(session)
    db_user = await UserRepository(session).get_by_id(user.id)
    assert db_user is not None
    updated = await service.disable_2fa(db_user, payload.code)
    return UserRead.model_validate(updated)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: PasswordChangeRequest,
    user: CurrentUser,
    session: DbSession,
) -> None:
    from app.repositories.user import UserRepository

    service = AuthService(session)
    db_user = await UserRepository(session).get_by_id(user.id)
    assert db_user is not None
    await service.change_password(
        db_user,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
