from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.host import Host
    from app.models.user import User


class PluginInstall(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Per-user install of an out-of-process plugin (daemon)."""

    __tablename__ = "plugin_installs"
    __table_args__ = (
        UniqueConstraint("user_id", "plugin_id", name="uq_plugin_installs_user_plugin"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plugin_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="active",
        server_default="active",
    )
    is_daemon_online: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    manifest: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    daemon_token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    daemon_token_prefix: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    owner: Mapped[User] = relationship("User", back_populates="plugin_installs")
    host_bindings: Mapped[list[PluginHostBinding]] = relationship(
        "PluginHostBinding",
        back_populates="install",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class PluginHostBinding(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Per-host configuration for a plugin install."""

    __tablename__ = "plugin_host_bindings"
    __table_args__ = (
        UniqueConstraint(
            "install_id",
            "host_id",
            name="uq_plugin_host_bindings_install_host",
        ),
    )

    install_id: Mapped[UUID] = mapped_column(
        ForeignKey("plugin_installs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    host_id: Mapped[UUID] = mapped_column(
        ForeignKey("hosts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    install: Mapped[PluginInstall] = relationship(
        "PluginInstall",
        back_populates="host_bindings",
    )
    host: Mapped[Host] = relationship("Host")
