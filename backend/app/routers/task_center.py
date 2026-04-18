"""异步任务状态中心 API"""

from fastapi import APIRouter
from app.services.task_center import get_task, list_tasks, get_stats

router = APIRouter(prefix="/api/tasks", tags=["task-center"])


@router.get("")
async def list_all_tasks(
    project_id: str | None = None,
    task_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
):
    return list_tasks(project_id, task_type, status, limit)


@router.get("/stats")
async def task_stats(project_id: str | None = None):
    return get_stats(project_id)


@router.get("/{task_id}")
async def get_task_detail(task_id: str):
    task = get_task(task_id)
    if not task:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="任务不存在")
    return task
