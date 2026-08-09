"""Public status page schemas — no IPs, credentials, or private metadata."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PublicTelemetry(BaseModel):
    cpu_percent: float | None = None
    ram_percent: float | None = None
    net_bytes_sent: int | None = None
    net_bytes_recv: int | None = None
    uptime_seconds: int | None = None
    collected_at: datetime | None = None


class PublicBilling(BaseModel):
    enabled: bool = True
    cycle: str | None = None
    custom_days: int | None = None
    renewal_at: date | None = None
    amount: float | None = None
    currency: str | None = None
    auto_renew: bool = False


class PublicEnergyDay(BaseModel):
    day: date
    value: float


class PublicEnergy(BaseModel):
    metric: str = "energy_kwh"
    unit: str = "kWh"
    today_kwh: float | None = None
    month_kwh: float | None = None
    calendar: list[PublicEnergyDay] = Field(default_factory=list)


class PublicHost(BaseModel):
    id: UUID
    name: str
    country_code: str | None = None
    agent_online: bool = False
    telemetry: PublicTelemetry | None = None
    billing: PublicBilling | None = None
    energy: PublicEnergy | None = None


class PublicStatusPage(BaseModel):
    slug: str = Field(min_length=2, max_length=64)
    hosts: list[PublicHost] = []
