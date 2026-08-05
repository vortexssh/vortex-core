from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models.user import User


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str
    totp_code: str | None = Field(default=None, min_length=6, max_length=8)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    public_slug: str | None = None
    is_2fa_enabled: bool
    is_email_verified: bool
    is_active: bool
    preferred_currency: str = "USD"
    telegram_linked: bool = False
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def map_telegram_linked(cls, data: Any) -> Any:
        if isinstance(data, User):
            return {
                "id": data.id,
                "email": data.email,
                "public_slug": data.public_slug,
                "is_2fa_enabled": data.is_2fa_enabled,
                "is_email_verified": data.is_email_verified,
                "is_active": data.is_active,
                "preferred_currency": data.preferred_currency,
                "telegram_linked": data.telegram_chat_id is not None,
                "created_at": data.created_at,
            }
        return data


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    public_slug: str | None = Field(default=None, max_length=64)
    preferred_currency: str | None = Field(default=None, min_length=3, max_length=3)

    @field_validator("preferred_currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        code = value.strip().upper()
        if len(code) != 3 or not code.isalpha():
            raise ValueError("preferred_currency must be ISO-4217 alpha-3")
        return code


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RegisterResponse(BaseModel):
    email: EmailStr
    message: str = "Check your inbox to confirm your email"


class EmailVerifyRequest(BaseModel):
    token: str = Field(min_length=16, max_length=128)


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class TotpSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class TotpVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class TotpDisableRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)
