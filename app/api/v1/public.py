from fastapi import APIRouter, Request

from app.api.deps import DbSession, RedisClient
from app.core.rate_limit import client_ip, rate_limiter
from app.schemas.public import PublicStatusPage
from app.services.public import PublicStatusService

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/u/{slug}", response_model=PublicStatusPage)
async def get_public_status(
    slug: str,
    request: Request,
    session: DbSession,
    redis: RedisClient,
) -> PublicStatusPage:
    rate_limiter.check(
        f"public-status:{client_ip(request)}",
        limit=120,
        window_seconds=60,
    )
    service = PublicStatusService(session, redis)
    return await service.get_page(slug)
