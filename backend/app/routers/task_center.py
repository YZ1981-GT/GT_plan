"""异步任务状态中心 API"""

from fastapi import APIRouter, Depends
from app.deps import get_current_user
from app.models.core import User
from app.services.task_center import get_task, list_tasks, get_stats

router = APIRouter(prefix="/api/tasks", tags=["task-center"])


@router.get("")
async def list_all_tasks(
    project_id: str | None = None,
    task_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
):
    return list_tasks(project_id, task_type, status, limit)


@router.get("/stats")
async def task_stats(project_id: str | None = None, current_user: User = Depends(get_current_user)):
    return get_stats(project_id)


@router.get("/{task_id}")
async def get_task_detail(task_id: str, current_user: User = Depends(get_current_user)):
    task = get_task(task_id)
    if not task:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.post("/{task_id}/retry")
async def retry_failed_task(task_id: str, current_user: User = Depends(get_current_user)):
    """人工重试失败任务"""
    from fastapi import HTTPException
    from app.services.task_center import retry_task
    result = retry_task(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
