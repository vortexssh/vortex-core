from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


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
    is_active: bool
    created_at: datetime


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    public_slug: str | None = Field(default=None, max_length=64)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


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
