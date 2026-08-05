"""Host billing, reminders & spend control.

Revision ID: 0006_host_billing
Revises: 0005_host_sort_order
Create Date: 2026-08-05

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_host_billing"
down_revision: str | None = "0005_host_sort_order"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "hosts",
        sa.Column("billing_enabled", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column("hosts", sa.Column("billing_cycle", sa.String(length=32), nullable=True))
    op.add_column("hosts", sa.Column("billing_custom_days", sa.Integer(), nullable=True))
    op.add_column("hosts", sa.Column("billing_renewal_at", sa.Date(), nullable=True))
    op.add_column(
        "hosts",
        sa.Column("billing_amount", sa.Numeric(precision=12, scale=2), nullable=True),
    )
    op.add_column("hosts", sa.Column("billing_currency", sa.String(length=3), nullable=True))
    op.add_column(
        "hosts",
        sa.Column("billing_auto_renew", sa.Boolean(), server_default="true", nullable=False),
    )
    op.add_column("hosts", sa.Column("billing_notes", sa.Text(), nullable=True))
    op.create_index("ix_hosts_billing_renewal_at", "hosts", ["billing_renewal_at"])

    op.add_column(
        "users",
        sa.Column(
            "preferred_currency",
            sa.String(length=3),
            server_default="USD",
            nullable=False,
        ),
    )
    op.add_column("users", sa.Column("telegram_chat_id", sa.String(length=64), nullable=True))
    op.add_column(
        "users",
        sa.Column("telegram_linked_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "user_notification_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("email_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("telegram_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("in_app_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("client_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "reminder_offsets_days",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[7, 3, 1, 0]",
            nullable=False,
        ),
        sa.Column(
            "billing_reminders_enabled",
            sa.Boolean(),
            server_default="true",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(
        "ix_user_notification_settings_user_id",
        "user_notification_settings",
        ["user_id"],
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("host_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("dedupe_key", sa.String(length=128), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["host_id"], ["hosts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "host_id",
            "kind",
            "dedupe_key",
            name="uq_notifications_dedupe",
        ),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_host_id", "notifications", ["host_id"])

    op.create_table(
        "telegram_link_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_telegram_link_codes_user_id", "telegram_link_codes", ["user_id"])
    op.create_index("ix_telegram_link_codes_code", "telegram_link_codes", ["code"])


def downgrade() -> None:
    op.drop_index("ix_telegram_link_codes_code", table_name="telegram_link_codes")
    op.drop_index("ix_telegram_link_codes_user_id", table_name="telegram_link_codes")
    op.drop_table("telegram_link_codes")
    op.drop_index("ix_notifications_host_id", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index(
        "ix_user_notification_settings_user_id",
        table_name="user_notification_settings",
    )
    op.drop_table("user_notification_settings")
    op.drop_column("users", "telegram_linked_at")
    op.drop_column("users", "telegram_chat_id")
    op.drop_column("users", "preferred_currency")
    op.drop_index("ix_hosts_billing_renewal_at", table_name="hosts")
    op.drop_column("hosts", "billing_notes")
    op.drop_column("hosts", "billing_auto_renew")
    op.drop_column("hosts", "billing_currency")
    op.drop_column("hosts", "billing_amount")
    op.drop_column("hosts", "billing_renewal_at")
    op.drop_column("hosts", "billing_custom_days")
    op.drop_column("hosts", "billing_cycle")
    op.drop_column("hosts", "billing_enabled")
