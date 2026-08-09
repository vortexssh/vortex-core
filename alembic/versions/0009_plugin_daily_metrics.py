"""Plugin daily metric aggregates (PostgreSQL).

Revision ID: 0009_plugin_daily_metrics
Revises: 0008_plugins
Create Date: 2026-08-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_plugin_daily_metrics"
down_revision: str | None = "0008_plugins"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plugin_daily_metrics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("install_id", sa.Uuid(), nullable=False),
        sa.Column("host_id", sa.Uuid(), nullable=True),
        sa.Column("metric", sa.String(length=64), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
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
        sa.ForeignKeyConstraint(
            ["host_id"],
            ["hosts.id"],
            name=op.f("fk_plugin_daily_metrics_host_id_hosts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["install_id"],
            ["plugin_installs.id"],
            name=op.f("fk_plugin_daily_metrics_install_id_plugin_installs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plugin_daily_metrics")),
        sa.UniqueConstraint(
            "install_id",
            "host_id",
            "metric",
            "day",
            name="uq_plugin_daily_metrics_install_host_metric_day",
        ),
    )
    op.create_index(
        op.f("ix_plugin_daily_metrics_install_id"),
        "plugin_daily_metrics",
        ["install_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_plugin_daily_metrics_host_id"),
        "plugin_daily_metrics",
        ["host_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_plugin_daily_metrics_metric"),
        "plugin_daily_metrics",
        ["metric"],
        unique=False,
    )
    op.create_index(
        op.f("ix_plugin_daily_metrics_day"),
        "plugin_daily_metrics",
        ["day"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_plugin_daily_metrics_day"), table_name="plugin_daily_metrics")
    op.drop_index(op.f("ix_plugin_daily_metrics_metric"), table_name="plugin_daily_metrics")
    op.drop_index(op.f("ix_plugin_daily_metrics_host_id"), table_name="plugin_daily_metrics")
    op.drop_index(
        op.f("ix_plugin_daily_metrics_install_id"),
        table_name="plugin_daily_metrics",
    )
    op.drop_table("plugin_daily_metrics")
