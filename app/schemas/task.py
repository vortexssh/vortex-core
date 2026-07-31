from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.task import TaskLogStatus


class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    command: str = Field(min_length=1)
    cron_expr: str | None = Field(default=None, max_length=128)
    is_active: bool = True


class TaskUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    command: str | None = Field(default=None, min_length=1)
    cron_expr: str | None = Field(default=None, max_length=128)
    is_active: bool | None = None


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    host_id: UUID
    name: str
    command: str
    cron_expr: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TaskLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    executed_at: datetime
    status: TaskLogStatus
    exit_code: int | None
    stdout: str | None
    stderr: str | None


class TelemetryRead(BaseModel):
    host_id: UUID
    cpu_percent: float | None = None
    ram_percent: float | None = None
    ram_used_bytes: int | None = None
    ram_total_bytes: int | None = None
    net_bytes_sent: int | None = None
    net_bytes_recv: int | None = None
    uptime_seconds: int | None = None
    collected_at: datetime | None = None
