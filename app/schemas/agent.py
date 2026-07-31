from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AgentCreated(BaseModel):
    id: UUID
    host_id: UUID
    secret: str
    version: str | None = None
    is_online: bool = False


class AgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    host_id: UUID
    version: str | None
    is_online: bool
    last_seen_at: datetime | None
    created_at: datetime


class AgentRotateResponse(BaseModel):
    id: UUID
    host_id: UUID
    secret: str
