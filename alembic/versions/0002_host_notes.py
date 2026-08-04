"""Add optional notes text on hosts.

Revision ID: 0002_host_notes
Revises: 0001_initial
Create Date: 2026-08-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_host_notes"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("hosts", sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("hosts", "notes")
