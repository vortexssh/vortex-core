from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.api_key import ApiKey
    from app.models.host import Host
    from app.models.notification import Notification, UserNotificationSettings
    from app.models.plugin import PluginInstall
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
    require_2fa: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
        doc="When false, skip TOTP at login and UserWith2FA / tunnel 2FA gates (debug).",
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
    preferred_currency: Mapped[str] = mapped_column(
        String(3),
        default="USD",
        server_default="USD",
        nullable=False,
    )
    telegram_chat_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    telegram_linked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    hosts: Mapped[list[Host]] = relationship(
        "Host",
        back_populates="owner",
        cascade="all, delete-orphan",
        lazy="noload",
    )
    api_keys: Mapped[list[ApiKey]] = relationship(
        "ApiKey",
        back_populates="owner",
        cascade="all, delete-orphan",
        lazy="noload",
    )
    tags: Mapped[list[Tag]] = relationship(
        "Tag",
        back_populates="owner",
        cascade="all, delete-orphan",
        lazy="noload",
    )
    notification_settings: Mapped[UserNotificationSettings | None] = relationship(
        "UserNotificationSettings",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="noload",
    )
    notifications: Mapped[list[Notification]] = relationship(
        "Notification",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="noload",
    )
    plugin_installs: Mapped[list[PluginInstall]] = relationship(
        "PluginInstall",
        back_populates="owner",
        cascade="all, delete-orphan",
        lazy="noload",
    )
