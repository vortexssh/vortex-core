"""Public status page schemas — no IPs, credentials, or private metadata."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PublicTelemetry(BaseModel):
    cpu_percent: float | None = None
    ram_percent: float | None = None
    net_bytes_sent: int | None = None
    net_bytes_recv: int | None = None
    uptime_seconds: int | None = None
    collected_at: datetime | None = None


class PublicHost(BaseModel):
    id: UUID
    name: str
    country_code: str | None = None
    agent_online: bool = False
    telemetry: PublicTelemetry | None = None


class PublicStatusPage(BaseModel):
    slug: str = Field(min_length=2, max_length=64)
    hosts: list[PublicHost] = []
