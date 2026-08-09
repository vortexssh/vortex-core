from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


ALLOWED_PERMISSIONS = frozenset(
    {
        "host.bind",
        "state.write",
        "rpc",
        "nav",
        "pages",
        "hosts.columns",
        "hosts.panels",
        "hosts.actions",
        "hosts.editor",
        "settings",
    }
)

ALLOWED_SLOTS = frozenset(
    {
        "nav.items",
        "routes",
        "hosts.table.columns",
        "hosts.row.actions",
        "hosts.detail.panels",
        "hosts.editor.fields",
        "settings.tabs",
        "host.actions",
    }
)

SLOT_PERMISSION: dict[str, str] = {
    "nav.items": "nav",
    "routes": "pages",
    "hosts.table.columns": "hosts.columns",
    "hosts.row.actions": "hosts.actions",
    "hosts.detail.panels": "hosts.panels",
    "hosts.editor.fields": "hosts.editor",
    "settings.tabs": "settings",
    "host.actions": "hosts.actions",
}


class PluginRpcMethod(BaseModel):
    method: str = Field(min_length=1, max_length=64)
    input: str | None = None
    output: str | None = None


class PluginUiContribution(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    slot: str
    id: str = Field(min_length=1, max_length=64)
    item: dict[str, Any] | None = None
    route: str | None = None
    view: str | dict[str, Any] | None = None
    column: dict[str, Any] | None = None
    action: dict[str, Any] | None = None
    schema_ref: str | dict[str, Any] | None = Field(
        default=None,
        alias="schema",
        description="JSON Schema object or path key into manifest.schemas",
    )
    label: str | None = None
    requires_host_binding: bool = False

    @field_validator("slot")
    @classmethod
    def validate_slot(cls, value: str) -> str:
        if value not in ALLOWED_SLOTS:
            raise ValueError(f"Unknown slot: {value}")
        return value


class PluginUiBlock(BaseModel):
    contributions: list[PluginUiContribution] = Field(default_factory=list)


class PluginManifest(BaseModel):
    """Validated vortex-plugin.json (api_version=1)."""

    id: str = Field(min_length=3, max_length=128, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    name: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=32)
    api_version: int = Field(default=1)
    permissions: list[str] = Field(default_factory=list)
    config_schema: dict[str, Any] | str | None = None
    host_binding_schema: dict[str, Any] | str | None = None
    rpc: list[PluginRpcMethod] = Field(default_factory=list)
    ui: PluginUiBlock = Field(default_factory=PluginUiBlock)
    views: dict[str, Any] = Field(
        default_factory=dict,
        description="Inline declarative views keyed by path (e.g. ui/pages/home.json)",
    )
    schemas: dict[str, Any] = Field(
        default_factory=dict,
        description="Inline JSON Schemas keyed by path",
    )

    @field_validator("api_version")
    @classmethod
    def only_v1(cls, value: int) -> int:
        if value != 1:
            raise ValueError("Only api_version=1 is supported")
        return value

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, value: list[str]) -> list[str]:
        unknown = set(value) - ALLOWED_PERMISSIONS
        if unknown:
            raise ValueError(f"Unknown permissions: {', '.join(sorted(unknown))}")
        return list(dict.fromkeys(value))


class PluginInstallCreate(BaseModel):
    manifest: PluginManifest
    config: dict[str, Any] = Field(default_factory=dict)


class PluginInstallUpdate(BaseModel):
    status: str | None = Field(default=None, pattern=r"^(active|disabled)$")
    config: dict[str, Any] | None = None
    manifest: PluginManifest | None = None


class PluginHostBindingUpsert(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)


class PluginHostBindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    install_id: UUID
    host_id: UUID
    config: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class PluginInstallRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plugin_id: str
    name: str
    version: str
    status: str
    is_daemon_online: bool
    config: dict[str, Any]
    manifest: dict[str, Any]
    host_bindings: list[PluginHostBindingRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class PluginInstallCreated(PluginInstallRead):
    """Returned once with the raw daemon token."""

    daemon_token: str


class PluginDaemonStatePush(BaseModel):
    host_id: UUID | None = None
    state: dict[str, Any] = Field(default_factory=dict)
    history_key: str | None = Field(
        default=None,
        max_length=64,
        description="Optional Redis history list key suffix",
    )


class PluginStateRead(BaseModel):
    install_id: UUID
    host_id: UUID | None = None
    state: dict[str, Any] = Field(default_factory=dict)
    updated_at: str | None = None


class PluginRpcRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)
    host_id: UUID | None = None


class PluginRpcResponse(BaseModel):
    result: dict[str, Any] = Field(default_factory=dict)


class PluginUiContributionResolved(BaseModel):
    install_id: UUID
    plugin_id: str
    plugin_name: str
    slot: str
    contribution_id: str
    payload: dict[str, Any]
    requires_host_binding: bool = False
    view: dict[str, Any] | None = None


class PluginUiBundle(BaseModel):
    installs: list[PluginInstallRead]
    contributions: list[PluginUiContributionResolved]


class PluginDaemonBindingRead(BaseModel):
    host_id: UUID
    config: dict[str, Any] = Field(default_factory=dict)


class PluginDailySample(BaseModel):
    host_id: UUID | None = None
    metric: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    day: date
    value: float
    meta: dict[str, Any] = Field(default_factory=dict)


class PluginDailyMetricsUpsert(BaseModel):
    samples: list[PluginDailySample] = Field(min_length=1, max_length=500)


class PluginDailyMetricRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    install_id: UUID
    host_id: UUID | None
    metric: str
    day: date
    value: float
    meta: dict[str, Any] = Field(default_factory=dict)


class PluginDailyMetricsList(BaseModel):
    samples: list[PluginDailyMetricRead] = Field(default_factory=list)
