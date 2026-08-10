"""Add users.require_2fa (default true) for debug bypass of 2FA gates.

Revision ID: 0010_user_require_2fa
Revises: 0009_plugin_daily_metrics
Create Date: 2026-08-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0010_user_require_2fa"
down_revision: str | None = "0009_plugin_daily_metrics"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "require_2fa",
            sa.Boolean(),
            server_default="true",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "require_2fa")
