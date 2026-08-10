from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

BillingCycleLiteral = Literal["monthly", "quarterly", "semiannual", "annual", "custom"]


def _normalize_currency(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    code = value.strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise ValueError("currency must be ISO-4217 alpha-3")
    return code


class NotificationSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    email_enabled: bool
    telegram_enabled: bool
    in_app_enabled: bool
    client_enabled: bool
    reminder_offsets_days: list[int]
    billing_reminders_enabled: bool
    notify_login: bool
    notify_password_changed: bool
    notify_2fa_enabled: bool
    notify_2fa_disabled: bool
    notify_profile_updated: bool
    notify_telegram_linked: bool
    notify_telegram_unlinked: bool
    notify_host_created: bool
    notify_host_updated: bool
    notify_host_deleted: bool
    notify_agent_created: bool
    notify_agent_rotated: bool
    notify_agent_revoked: bool
    notify_api_key_created: bool
    notify_api_key_deleted: bool
    notify_task_created: bool
    notify_task_updated: bool
    notify_task_deleted: bool
    notify_billing_advanced: bool
    notify_billing_auto_renewed: bool


class NotificationSettingsUpdate(BaseModel):
    email_enabled: bool | None = None
    telegram_enabled: bool | None = None
    in_app_enabled: bool | None = None
    client_enabled: bool | None = None
    reminder_offsets_days: list[int] | None = None
    billing_reminders_enabled: bool | None = None
    notify_login: bool | None = None
    notify_password_changed: bool | None = None
    notify_2fa_enabled: bool | None = None
    notify_2fa_disabled: bool | None = None
    notify_profile_updated: bool | None = None
    notify_telegram_linked: bool | None = None
    notify_telegram_unlinked: bool | None = None
    notify_host_created: bool | None = None
    notify_host_updated: bool | None = None
    notify_host_deleted: bool | None = None
    notify_agent_created: bool | None = None
    notify_agent_rotated: bool | None = None
    notify_agent_revoked: bool | None = None
    notify_api_key_created: bool | None = None
    notify_api_key_deleted: bool | None = None
    notify_task_created: bool | None = None
    notify_task_updated: bool | None = None
    notify_task_deleted: bool | None = None
    notify_billing_advanced: bool | None = None
    notify_billing_auto_renewed: bool | None = None

    @field_validator("reminder_offsets_days")
    @classmethod
    def validate_offsets(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        cleaned = sorted({int(v) for v in value if int(v) >= 0})
        if not cleaned:
            raise ValueError("At least one reminder offset (days >= 0) is required")
        if len(cleaned) > 14:
            raise ValueError("Too many reminder offsets")
        return cleaned


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    host_id: UUID | None = None
    kind: str
    title: str
    body: str
    payload: dict[str, Any] | None = None
    read_at: datetime | None = None
    created_at: datetime


class TelegramLinkResponse(BaseModel):
    code: str
    deep_link: str
    # Opens Telegram Desktop / mobile; avoids t.me → telegram.org browser redirect.
    tg_link: str
    expires_at: datetime
    bot_username: str | None = None


class TelegramConfirmRequest(BaseModel):
    code: str = Field(min_length=4, max_length=16)
    chat_id: str = Field(min_length=1, max_length=64)


class TelegramStatusRead(BaseModel):
    linked: bool
    chat_id: str | None = None
    linked_at: datetime | None = None
    bot_username: str | None = None


class BillingHostBrief(BaseModel):
    id: UUID
    name: str
    billing_amount: Decimal | None = None
    billing_currency: str | None = None
    amount_converted: Decimal | None = None
    country_code: str | None = None
    # True = stored next renewal; False = projected future occurrence
    is_next: bool = True
    cycle: str | None = None
    payer_id: UUID | None = None
    payer_name: str | None = None


class BillingDay(BaseModel):
    date: date
    hosts: list[BillingHostBrief]


class BillingCalendarResponse(BaseModel):
    year: int
    month: int
    currency: str
    days: list[BillingDay]
    payer_id: UUID | None = None
    payer_name: str | None = None


class BillingSummaryItem(BaseModel):
    host_id: UUID
    host_name: str
    amount: Decimal
    currency: str
    amount_converted: Decimal | None
    renewal_at: date | None
    cycle: str | None


class BillingSummaryResponse(BaseModel):
    currency: str
    from_date: date
    to_date: date
    total: Decimal
    items: list[BillingSummaryItem]
    skipped: list[str] = Field(default_factory=list)
    payer_id: UUID | None = None
    payer_name: str | None = None


class BillingPayerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    notes: str | None = Field(default=None, max_length=4096)

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class BillingPayerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    notes: str | None = Field(default=None, max_length=4096)

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class BillingPayerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    notes: str | None = None
    host_count: int = 0
    created_at: datetime
    updated_at: datetime


class BillingPayerHostBrief(BaseModel):
    id: UUID
    name: str
    billing_enabled: bool
    billing_amount: Decimal | None = None
    billing_currency: str | None = None
    billing_renewal_at: date | None = None
    billing_cycle: BillingCycleLiteral | None = None
    billing_auto_renew: bool = True
    country_code: str | None = None


class BillingPayerDetail(BillingPayerRead):
    hosts: list[BillingPayerHostBrief] = Field(default_factory=list)


class BillingFieldsMixin(BaseModel):
    billing_enabled: bool | None = None
    billing_cycle: BillingCycleLiteral | None = None
    billing_custom_days: int | None = Field(default=None, ge=1, le=3660)
    billing_renewal_at: date | None = None
    billing_amount: Decimal | None = Field(default=None, ge=0)
    billing_currency: str | None = Field(default=None, min_length=3, max_length=3)
    billing_auto_renew: bool | None = None
    billing_notes: str | None = Field(default=None, max_length=4096)

    @field_validator("billing_currency")
    @classmethod
    def normalize_billing_currency(cls, value: str | None) -> str | None:
        return _normalize_currency(value)

    @field_validator("billing_notes")
    @classmethod
    def normalize_billing_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


def assert_billing_enabled_complete(
    *,
    billing_enabled: bool | None,
    billing_cycle: str | None,
    billing_custom_days: int | None,
    billing_renewal_at: date | None,
    billing_amount: Decimal | None,
    billing_currency: str | None,
) -> None:
    if not billing_enabled:
        return
    if not billing_cycle:
        raise ValueError("billing_cycle is required when billing is enabled")
    if billing_cycle == "custom" and not billing_custom_days:
        raise ValueError("billing_custom_days is required for custom cycle")
    if billing_renewal_at is None:
        raise ValueError("billing_renewal_at is required when billing is enabled")
    if billing_amount is None:
        raise ValueError("billing_amount is required when billing is enabled")
    if not billing_currency:
        raise ValueError("billing_currency is required when billing is enabled")
