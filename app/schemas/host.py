from datetime import date, datetime
from decimal import Decimal
from ipaddress import IPv4Address, IPv6Address
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.billing import BillingCycleLiteral, BillingFieldsMixin, assert_billing_enabled_complete


class BillingPayerBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str


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


class HostCreate(BillingFieldsMixin):
    name: str = Field(min_length=1, max_length=128)
    ip_address: str | None = None
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=64)
    notes: str | None = Field(default=None, max_length=16_384)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    is_hidden: bool = False
    is_proxy_enabled: bool = False
    billing_enabled: bool = False
    billing_auto_renew: bool = True
    billing_payer_id: UUID | None = None

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

    @model_validator(mode="after")
    def validate_billing(self) -> "HostCreate":
        assert_billing_enabled_complete(
            billing_enabled=self.billing_enabled,
            billing_cycle=self.billing_cycle,
            billing_custom_days=self.billing_custom_days,
            billing_renewal_at=self.billing_renewal_at,
            billing_amount=self.billing_amount,
            billing_currency=self.billing_currency,
        )
        return self


class HostUpdate(BillingFieldsMixin):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    ip_address: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, min_length=1, max_length=64)
    notes: str | None = Field(default=None, max_length=16_384)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    is_hidden: bool | None = None
    billing_payer_id: UUID | None = None

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

    @model_validator(mode="after")
    def validate_billing_on_enable(self) -> "HostUpdate":
        if self.billing_enabled is True:
            assert_billing_enabled_complete(
                billing_enabled=True,
                billing_cycle=self.billing_cycle,
                billing_custom_days=self.billing_custom_days,
                billing_renewal_at=self.billing_renewal_at,
                billing_amount=self.billing_amount,
                billing_currency=self.billing_currency,
            )
        return self


class HostProxyToggle(BaseModel):
    is_proxy_enabled: bool


class HostHiddenToggle(BaseModel):
    is_hidden: bool


class HostReorder(BaseModel):
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
    billing_enabled: bool = False
    billing_cycle: BillingCycleLiteral | None = None
    billing_custom_days: int | None = None
    billing_renewal_at: date | None = None
    billing_amount: Decimal | None = None
    billing_currency: str | None = None
    billing_auto_renew: bool = True
    billing_notes: str | None = None
    billing_payer_id: UUID | None = None
    payer: BillingPayerBrief | None = None
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

    @model_validator(mode="wrap")
    @classmethod
    def attach_payer(cls, data: Any, handler) -> "HostRead":
        from app.models.host import Host

        read = handler(data)
        if isinstance(data, Host) and data.billing_payer is not None:
            return read.model_copy(
                update={
                    "payer": BillingPayerBrief.model_validate(data.billing_payer),
                }
            )
        return read


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
    tag_ids: list[UUID] = Field(default_factory=list)


class TagFullRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    color: str
    created_at: datetime
