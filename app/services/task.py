from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task, TaskLog, TaskLogStatus
from app.repositories.host import HostRepository
from app.repositories.task import TaskRepository
from app.schemas.task import TaskCreate, TaskUpdate


class TaskService:
    def __init__(self, session: AsyncSession) -> None:
        self._tasks = TaskRepository(session)
        self._hosts = HostRepository(session)
        self._session = session

    async def list_for_host(self, user_id: UUID, host_id: UUID) -> list[Task]:
        host = await self._hosts.get_by_id(host_id, user_id)
        if host is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "host_not_found", "message": "Host not found"},
            )
        return await self._tasks.list_for_host(host_id, user_id)

    async def create(self, user_id: UUID, host_id: UUID, payload: TaskCreate) -> Task:
        host = await self._hosts.get_by_id(host_id, user_id)
        if host is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "host_not_found", "message": "Host not found"},
            )
        task = Task(
            host_id=host_id,
            name=payload.name,
            command=payload.command,
            cron_expr=payload.cron_expr,
            is_active=payload.is_active,
        )
        task = await self._tasks.create(task)
        await self._session.commit()
        from app.models.billing import NotificationKind
        from app.services.notifications import notify_user

        await notify_user(
            self._session,
            user_id,
            kind=NotificationKind.TASK_CREATED,
            title="Task created",
            body=f"Scheduled task «{task.name}» was created.",
            host_id=host_id,
        )
        return task

    async def get(self, user_id: UUID, task_id: UUID) -> Task:
        task = await self._tasks.get_by_id(task_id, user_id)
        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "task_not_found", "message": "Task not found"},
            )
        return task

    async def update(self, user_id: UUID, task_id: UUID, payload: TaskUpdate) -> Task:
        task = await self.get(user_id, task_id)
        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(task, key, value)
        await self._tasks.save(task)
        await self._session.commit()
        from app.models.billing import NotificationKind
        from app.services.notifications import notify_user

        await notify_user(
            self._session,
            user_id,
            kind=NotificationKind.TASK_UPDATED,
            title="Task updated",
            body=f"Scheduled task «{task.name}» was updated.",
            host_id=task.host_id,
        )
        return task

    async def delete(self, user_id: UUID, task_id: UUID) -> None:
        task = await self.get(user_id, task_id)
        name = task.name
        host_id = task.host_id
        await self._tasks.delete(task)
        await self._session.commit()
        from app.models.billing import NotificationKind
        from app.services.notifications import notify_user

        await notify_user(
            self._session,
            user_id,
            kind=NotificationKind.TASK_DELETED,
            title="Task deleted",
            body=f"Scheduled task «{name}» was deleted.",
            host_id=host_id,
        )

    async def list_logs(self, user_id: UUID, task_id: UUID) -> list[TaskLog]:
        await self.get(user_id, task_id)
        return await self._tasks.list_logs(task_id)

    async def record_result(
        self,
        task_id: UUID,
        *,
        status_value: TaskLogStatus,
        exit_code: int | None,
        stdout: str | None,
        stderr: str | None,
    ) -> TaskLog:
        log = TaskLog(
            task_id=task_id,
            status=status_value,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
        )
        log = await self._tasks.add_log(log)
        await self._session.commit()
        return log
