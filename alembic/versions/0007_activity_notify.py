"""Per-event activity notification toggles.

Revision ID: 0007_activity_notify
Revises: 0006_host_billing
Create Date: 2026-08-05

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_activity_notify"
down_revision: str | None = "0006_host_billing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EVENT_COLUMNS = (
    "notify_login",
    "notify_password_changed",
    "notify_2fa_enabled",
    "notify_2fa_disabled",
    "notify_profile_updated",
    "notify_telegram_linked",
    "notify_telegram_unlinked",
    "notify_host_created",
    "notify_host_updated",
    "notify_host_deleted",
    "notify_agent_created",
    "notify_agent_rotated",
    "notify_agent_revoked",
    "notify_api_key_created",
    "notify_api_key_deleted",
    "notify_task_created",
    "notify_task_updated",
    "notify_task_deleted",
    "notify_billing_advanced",
    "notify_billing_auto_renewed",
)


def upgrade() -> None:
    for name in _EVENT_COLUMNS:
        op.add_column(
            "user_notification_settings",
            sa.Column(name, sa.Boolean(), server_default="true", nullable=False),
        )


def downgrade() -> None:
    for name in reversed(_EVENT_COLUMNS):
        op.drop_column("user_notification_settings", name)
