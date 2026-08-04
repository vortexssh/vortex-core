from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Column, ForeignKey, String, Table, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.host import Host
    from app.models.user import User


host_tags = Table(
    "host_tags",
    Base.metadata,
    Column(
        "host_id",
        ForeignKey("hosts.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Tag(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """User-scoped host grouping tags."""

    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_tags_user_id_name"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#00FF00")

    owner: Mapped[User] = relationship("User", back_populates="tags")
    # Never selectin-load hosts here — that fans out into Host.tags/agent/tasks
    # on every GET /tags and breaks clients under load.
    hosts: Mapped[list[Host]] = relationship(
        "Host",
        secondary=host_tags,
        back_populates="tags",
        lazy="noload",
    )
