"""billing_payers + hosts.billing_payer_id

Revision ID: 0011_billing_payers
Revises: 0010_user_require_2fa
Create Date: 2026-08-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0011_billing_payers"
down_revision: str | None = "0010_user_require_2fa"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "billing_payers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
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
            name=op.f("fk_billing_payers_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_billing_payers")),
    )
    op.create_index(
        op.f("ix_billing_payers_user_id"),
        "billing_payers",
        ["user_id"],
        unique=False,
    )

    op.add_column(
        "hosts",
        sa.Column("billing_payer_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        op.f("ix_hosts_billing_payer_id"),
        "hosts",
        ["billing_payer_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_hosts_billing_payer_id_billing_payers"),
        "hosts",
        "billing_payers",
        ["billing_payer_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_hosts_billing_payer_id_billing_payers"),
        "hosts",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_hosts_billing_payer_id"), table_name="hosts")
    op.drop_column("hosts", "billing_payer_id")
    op.drop_index(op.f("ix_billing_payers_user_id"), table_name="billing_payers")
    op.drop_table("billing_payers")
