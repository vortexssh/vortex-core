"""Plugin installs, host bindings, and daemon tokens.

Revision ID: 0008_plugins
Revises: 0007_activity_notify
Create Date: 2026-08-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_plugins"
down_revision: str | None = "0007_activity_notify"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plugin_installs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("plugin_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="active",
            nullable=False,
        ),
        sa.Column(
            "is_daemon_online",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "manifest",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("daemon_token_hash", sa.Text(), nullable=False),
        sa.Column("daemon_token_prefix", sa.String(length=16), nullable=False),
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
            ["user_id"],
            ["users.id"],
            name=op.f("fk_plugin_installs_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plugin_installs")),
        sa.UniqueConstraint(
            "user_id",
            "plugin_id",
            name="uq_plugin_installs_user_plugin",
        ),
    )
    op.create_index(
        op.f("ix_plugin_installs_user_id"),
        "plugin_installs",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_plugin_installs_plugin_id"),
        "plugin_installs",
        ["plugin_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_plugin_installs_daemon_token_prefix"),
        "plugin_installs",
        ["daemon_token_prefix"],
        unique=False,
    )

    op.create_table(
        "plugin_host_bindings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("install_id", sa.Uuid(), nullable=False),
        sa.Column("host_id", sa.Uuid(), nullable=False),
        sa.Column(
            "config",
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
            name=op.f("fk_plugin_host_bindings_host_id_hosts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["install_id"],
            ["plugin_installs.id"],
            name=op.f("fk_plugin_host_bindings_install_id_plugin_installs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plugin_host_bindings")),
        sa.UniqueConstraint(
            "install_id",
            "host_id",
            name="uq_plugin_host_bindings_install_host",
        ),
    )
    op.create_index(
        op.f("ix_plugin_host_bindings_install_id"),
        "plugin_host_bindings",
        ["install_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_plugin_host_bindings_host_id"),
        "plugin_host_bindings",
        ["host_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_plugin_host_bindings_host_id"),
        table_name="plugin_host_bindings",
    )
    op.drop_index(
        op.f("ix_plugin_host_bindings_install_id"),
        table_name="plugin_host_bindings",
    )
    op.drop_table("plugin_host_bindings")
    op.drop_index(
        op.f("ix_plugin_installs_daemon_token_prefix"),
        table_name="plugin_installs",
    )
    op.drop_index(op.f("ix_plugin_installs_plugin_id"), table_name="plugin_installs")
    op.drop_index(op.f("ix_plugin_installs_user_id"), table_name="plugin_installs")
    op.drop_table("plugin_installs")
