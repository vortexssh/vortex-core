"""Core-side cron scheduler that dispatches task_run to online agents."""

from __future__ import annotations

import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from croniter import croniter

from app.core.database import AsyncSessionLocal
from app.repositories.task import TaskRepository
from app.websocket.manager import connection_manager

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def _cron_is_due(cron_expr: str, now: datetime) -> bool:
    """True if cron would fire at this minute."""
    try:
        itr = croniter(cron_expr, now)
        prev = itr.get_prev(datetime)
        return (
            prev.year == now.year
            and prev.month == now.month
            and prev.day == now.day
            and prev.hour == now.hour
            and prev.minute == now.minute
        )
    except (ValueError, KeyError):
        return False


async def _tick_cron_tasks() -> None:
    now = datetime.now().replace(second=0, microsecond=0)
    async with AsyncSessionLocal() as session:
        repo = TaskRepository(session)
        tasks = await repo.list_active_cron()
        for task in tasks:
            if not task.cron_expr:
                continue
            if not _cron_is_due(task.cron_expr, now):
                continue
            agent = task.host.agent if task.host else None
            if agent is None or not agent.is_online:
                logger.debug("Skipping cron task %s — agent offline", task.id)
                continue
            if not await connection_manager.is_agent_online(agent.id):
                continue
            sent = await connection_manager.send_task_run(
                agent.id,
                task_id=task.id,
                command=task.command,
            )
            logger.info("Cron dispatch task=%s sent=%s", task.id, sent)


def start_scheduler() -> None:
    if scheduler.running:
        return
    scheduler.add_job(
        _tick_cron_tasks,
        CronTrigger(minute="*"),
        id="vortex_cron_tick",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info("Task scheduler started")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Task scheduler stopped")
