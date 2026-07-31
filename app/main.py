import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.database import engine
from app.core.exceptions import register_exception_handlers
from app.core.redis import close_redis, init_redis
from app.services.scheduler import start_scheduler, stop_scheduler
from app.websocket.manager import connection_manager
from app.websocket.routes import router as ws_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("vortex_core")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    redis = await init_redis()
    await connection_manager.bind_redis(redis)
    start_scheduler()
    logger.info("Vortex Core started")
    try:
        yield
    finally:
        stop_scheduler()
        await connection_manager.shutdown()
        await close_redis()
        await engine.dispose()
        logger.info("Vortex Core stopped")


def create_app() -> FastAPI:
    settings = get_settings()

    import app.models  # noqa: F401

    application = FastAPI(
        title=settings.app_name,
        version=__version__,
        debug=settings.debug,
        lifespan=lifespan,
        description=(
            "VortexSSH Core — metadata REST API and WebSocket Tunnel Router. "
            "Never stores target-server passwords or private SSH keys."
        ),
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(application)
    application.include_router(api_router, prefix=settings.api_v1_prefix)
    application.include_router(ws_router)
    return application


app = create_app()
