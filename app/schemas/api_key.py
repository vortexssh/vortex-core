from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    expires_at: datetime | None = None


class ApiKeyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    key_prefix: str
    expires_at: datetime | None
    created_at: datetime


class ApiKeyCreated(ApiKeyRead):
    """Returned once on creation — includes plaintext key."""

    key: str
