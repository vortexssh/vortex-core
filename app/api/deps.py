"""Shared FastAPI dependencies (DB session, Redis, auth)."""

from app.core.database import get_db_session

get_db = get_db_session

__all__ = ["get_db"]
