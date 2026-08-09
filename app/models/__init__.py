"""ORM models. Import concrete models here so metadata is registered."""

from app.models.agent import Agent
from app.models.api_key import ApiKey
from app.models.base import Base
from app.models.billing import BillingCycle, NotificationKind
from app.models.host import Host
from app.models.notification import Notification, TelegramLinkCode, UserNotificationSettings
from app.models.plugin import PluginHostBinding, PluginInstall
from app.models.tag import Tag, host_tags
from app.models.task import Task, TaskLog, TaskLogStatus
from app.models.user import User

__all__ = [
    "Agent",
    "ApiKey",
    "Base",
    "BillingCycle",
    "Host",
    "Notification",
    "NotificationKind",
    "PluginHostBinding",
    "PluginInstall",
    "Tag",
    "Task",
    "TaskLog",
    "TaskLogStatus",
    "TelegramLinkCode",
    "User",
    "UserNotificationSettings",
    "host_tags",
]
