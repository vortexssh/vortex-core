from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbSession, UserWith2FA
from app.schemas.task import TaskCreate, TaskLogRead, TaskRead, TaskUpdate
from app.services.agent import AgentService
from app.services.task import TaskService
from app.websocket.manager import connection_manager

router = APIRouter(tags=["tasks"])


@router.get("/hosts/{host_id}/tasks", response_model=list[TaskRead])
async def list_tasks(
    host_id: UUID,
    user: UserWith2FA,
    session: DbSession,
) -> list[TaskRead]:
    service = TaskService(session)
    tasks = await service.list_for_host(user.id, host_id)
    return [TaskRead.model_validate(t) for t in tasks]


@router.post(
    "/hosts/{host_id}/tasks",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_task(
    host_id: UUID,
    payload: TaskCreate,
    user: UserWith2FA,
    session: DbSession,
) -> TaskRead:
    service = TaskService(session)
    task = await service.create(user.id, host_id, payload)
    return TaskRead.model_validate(task)


@router.patch("/tasks/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: UUID,
    payload: TaskUpdate,
    user: UserWith2FA,
    session: DbSession,
) -> TaskRead:
    service = TaskService(session)
    task = await service.update(user.id, task_id, payload)
    return TaskRead.model_validate(task)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: UUID,
    user: UserWith2FA,
    session: DbSession,
) -> None:
    service = TaskService(session)
    await service.delete(user.id, task_id)


@router.get("/tasks/{task_id}/logs", response_model=list[TaskLogRead])
async def list_task_logs(
    task_id: UUID,
    user: UserWith2FA,
    session: DbSession,
) -> list[TaskLogRead]:
    service = TaskService(session)
    logs = await service.list_logs(user.id, task_id)
    return [TaskLogRead.model_validate(log) for log in logs]


@router.post("/tasks/{task_id}/run", response_model=TaskRead)
async def run_task(
    task_id: UUID,
    user: UserWith2FA,
    session: DbSession,
) -> TaskRead:
    service = TaskService(session)
    task = await service.get(user.id, task_id)
    agent_service = AgentService(session)
    agent = await agent_service.get_for_host(user.id, task.host_id)
    if not await connection_manager.is_agent_online(agent.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "agent_offline", "message": "Agent is offline"},
        )
    sent = await connection_manager.send_task_run(
        agent.id,
        task_id=task.id,
        command=task.command,
    )
    if not sent:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "agent_unreachable", "message": "Failed to reach agent"},
        )
    return TaskRead.model_validate(task)
