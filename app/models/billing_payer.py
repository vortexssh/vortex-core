from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.host import Host
    from app.models.user import User


class BillingPayer(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Who pays for one or more hosts (billing grouping)."""

    __tablename__ = "billing_payers"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    owner: Mapped[User] = relationship("User", back_populates="billing_payers")
    hosts: Mapped[list[Host]] = relationship(
        "Host",
        back_populates="billing_payer",
        lazy="noload",
    )
