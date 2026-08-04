"""Email verification flag for users.

Revision ID: 0004_email_verification
Revises: 0003_public_status
Create Date: 2026-08-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_email_verification"
down_revision: str | None = "0003_public_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_email_verified",
            sa.Boolean(),
            server_default="true",
            nullable=False,
        ),
    )
    # New signups set this to false in application code; existing rows stay verified.


def downgrade() -> None:
    op.drop_column("users", "is_email_verified")
