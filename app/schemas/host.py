from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    color: str


class AgentStatusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_online: bool
    last_seen_at: datetime | None
    version: str | None


class HostCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    ip_address: str | None = None
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=64)
    notes: str | None = Field(default=None, max_length=16_384)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    is_hidden: bool = False
    is_proxy_enabled: bool = False

    @model_validator(mode="before")
    @classmethod
    def reject_secrets(cls, data: object) -> object:
        if isinstance(data, dict):
            forbidden = {"password", "private_key", "ssh_key", "secret", "passphrase"}
            found = forbidden.intersection(data.keys())
            if found:
                raise ValueError(
                    f"Zero-trust: forbidden fields not accepted: {', '.join(sorted(found))}"
                )
        return data

    @field_validator("ip_address")
    @classmethod
    def validate_ip(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        try:
            IPv4Address(value)
        except ValueError:
            try:
                IPv6Address(value)
            except ValueError as exc:
                raise ValueError("Invalid IP address") from exc
        return value

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("country_code")
    @classmethod
    def normalize_country(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        code = value.strip().upper()
        if len(code) != 2 or not code.isalpha():
            raise ValueError("country_code must be ISO-3166 alpha-2")
        return code


class HostUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    ip_address: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, min_length=1, max_length=64)
    notes: str | None = Field(default=None, max_length=16_384)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    is_hidden: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_secrets(cls, data: object) -> object:
        if isinstance(data, dict):
            forbidden = {"password", "private_key", "ssh_key", "secret", "passphrase"}
            found = forbidden.intersection(data.keys())
            if found:
                raise ValueError(
                    f"Zero-trust: forbidden fields not accepted: {', '.join(sorted(found))}"
                )
        return data

    @field_validator("ip_address")
    @classmethod
    def validate_ip(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        try:
            IPv4Address(value)
        except ValueError:
            try:
                IPv6Address(value)
            except ValueError as exc:
                raise ValueError("Invalid IP address") from exc
        return value

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("country_code")
    @classmethod
    def normalize_country(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        code = value.strip().upper()
        if len(code) != 2 or not code.isalpha():
            raise ValueError("country_code must be ISO-3166 alpha-2")
        return code


class HostProxyToggle(BaseModel):
    is_proxy_enabled: bool


class HostHiddenToggle(BaseModel):
    is_hidden: bool


class HostReorder(BaseModel):
    """Ordered list of host IDs owned by the current user (full or subset)."""

    host_ids: list[UUID] = Field(min_length=1)


class HostRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    ip_address: str | None
    port: int
    username: str
    notes: str | None = None
    country_code: str | None = None
    sort_order: int = 0
    is_hidden: bool = False
    is_proxy_enabled: bool
    tags: list[TagRead] = []
    agent: AgentStatusRead | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("ip_address", mode="before")
    @classmethod
    def coerce_ip(cls, value: object) -> str | None:
        if value is None:
            return None
        return str(value)


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    color: str = Field(default="#00FF00", pattern=r"^#[0-9A-Fa-f]{6}$")

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Tag name cannot be empty")
        return cleaned


class TagUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Tag name cannot be empty")
        return cleaned


class HostTagsUpdate(BaseModel):
    """Replace the full set of tags on a host (atomic sync)."""

    tag_ids: list[UUID] = Field(default_factory=list)


class TagFullRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    color: str
    created_at: datetime
