from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.tag import host_tags

if TYPE_CHECKING:
    from app.models.agent import Agent
    from app.models.tag import Tag
    from app.models.task import Task
    from app.models.user import User


class Host(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Host metadata only — no passwords or private SSH keys (zero-trust)."""

    __tablename__ = "hosts"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    port: Mapped[int] = mapped_column(Integer, default=22, nullable=False)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    is_hidden: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )
    is_proxy_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )

    owner: Mapped[User] = relationship("User", back_populates="hosts")
    tags: Mapped[list[Tag]] = relationship(
        "Tag",
        secondary=host_tags,
        back_populates="hosts",
        lazy="selectin",
    )
    agent: Mapped[Agent | None] = relationship(
        "Agent",
        back_populates="host",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    tasks: Mapped[list[Task]] = relationship(
        "Task",
        back_populates="host",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
