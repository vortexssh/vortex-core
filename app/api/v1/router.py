from fastapi import APIRouter

from app.api.deps import RedisClient
from app.api.v1 import agents, api_keys, auth, hosts, tags, tasks, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(api_keys.router)
api_router.include_router(hosts.router)
api_router.include_router(tags.router)
api_router.include_router(agents.router)
api_router.include_router(tasks.router)


@api_router.get("/health", tags=["health"])
async def health_check(redis: RedisClient) -> dict[str, str]:
    """Liveness probe — verifies Redis connectivity."""
    await redis.ping()
    return {"status": "ok"}
