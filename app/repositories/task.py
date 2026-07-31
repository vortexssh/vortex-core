from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.host import Host
from app.models.task import Task, TaskLog


class TaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, task_id: UUID, user_id: UUID) -> Task | None:
        result = await self._session.execute(
            select(Task)
            .join(Host, Task.host_id == Host.id)
            .where(Task.id == task_id, Host.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_any(self, task_id: UUID) -> Task | None:
        result = await self._session.execute(
            select(Task).where(Task.id == task_id)
        )
        return result.scalar_one_or_none()

    async def list_for_host(self, host_id: UUID, user_id: UUID) -> list[Task]:
        result = await self._session.execute(
            select(Task)
            .join(Host, Task.host_id == Host.id)
            .where(Task.host_id == host_id, Host.user_id == user_id)
            .order_by(Task.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_active_cron(self) -> list[Task]:
        result = await self._session.execute(
            select(Task)
            .options(selectinload(Task.host).selectinload(Host.agent))
            .where(
                Task.is_active.is_(True),
                Task.cron_expr.is_not(None),
            )
        )
        return list(result.scalars().all())

    async def create(self, task: Task) -> Task:
        self._session.add(task)
        await self._session.flush()
        await self._session.refresh(task)
        return task

    async def save(self, task: Task) -> Task:
        self._session.add(task)
        await self._session.flush()
        await self._session.refresh(task)
        return task

    async def delete(self, task: Task) -> None:
        await self._session.delete(task)
        await self._session.flush()

    async def add_log(self, log: TaskLog) -> TaskLog:
        self._session.add(log)
        await self._session.flush()
        await self._session.refresh(log)
        return log

    async def list_logs(self, task_id: UUID, *, limit: int = 50) -> list[TaskLog]:
        result = await self._session.execute(
            select(TaskLog)
            .where(TaskLog.task_id == task_id)
            .order_by(TaskLog.executed_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
