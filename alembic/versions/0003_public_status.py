"""Public status page: user slug, host hidden flag, country code.

Revision ID: 0003_public_status
Revises: 0002_host_notes
Create Date: 2026-08-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_public_status"
down_revision: str | None = "0002_host_notes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("public_slug", sa.String(length=64), nullable=True),
    )
    op.create_index(op.f("ix_users_public_slug"), "users", ["public_slug"], unique=True)

    op.add_column(
        "hosts",
        sa.Column(
            "is_hidden",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )
    op.add_column(
        "hosts",
        sa.Column("country_code", sa.String(length=2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("hosts", "country_code")
    op.drop_column("hosts", "is_hidden")
    op.drop_index(op.f("ix_users_public_slug"), table_name="users")
    op.drop_column("users", "public_slug")
