"""Add sort_order for host roster ordering.

Revision ID: 0005_host_sort_order
Revises: 0004_email_verification
Create Date: 2026-08-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_host_sort_order"
down_revision: str | None = "0004_email_verification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "hosts",
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_index("ix_hosts_user_id_sort_order", "hosts", ["user_id", "sort_order"])


def downgrade() -> None:
    op.drop_index("ix_hosts_user_id_sort_order", table_name="hosts")
    op.drop_column("hosts", "sort_order")
