from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.api_key import ApiKey
    from app.models.host import Host
    from app.models.tag import Tag


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Registered account. Never stores target-server credentials (zero-trust)."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(320),
        unique=True,
        index=True,
        nullable=False,
    )
    public_slug: Mapped[str | None] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=True,
    )
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_2fa_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )
    is_email_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
    )

    hosts: Mapped[list[Host]] = relationship(
        "Host",
        back_populates="owner",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    api_keys: Mapped[list[ApiKey]] = relationship(
        "ApiKey",
        back_populates="owner",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    tags: Mapped[list[Tag]] = relationship(
        "Tag",
        back_populates="owner",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
