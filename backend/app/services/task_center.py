"""异步任务状态中心 — 统一管理 OCR/AI/解析/同步等后台任务

状态流转：pending → processing → success / failed → retrying → success / failed
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any
from enum import Enum

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    success = "success"
    failed = "failed"
    retrying = "retrying"


class TaskType(str, Enum):
    ocr = "ocr"
    ai_review = "ai_review"
    ai_fill = "ai_fill"
    ai_analysis = "ai_analysis"
    parse_workpaper = "parse_workpaper"
    prefill_workpaper = "prefill_workpaper"
    sync_upload = "sync_upload"
    export_word = "export_word"
    export_pdf = "export_pdf"
    aging_analysis = "aging_analysis"
    attachment_classify = "attachment_classify"


# 内存任务存储（生产环境应改为 Redis 或数据库）
_tasks: dict[str, dict[str, Any]] = {}
MAX_TASKS = 1000


def create_task(
    task_type: TaskType,
    project_id: str | None = None,
    object_id: str | None = None,
    params: dict | None = None,
) -> str:
    """创建任务，返回 task_id"""
    task_id = str(uuid.uuid4())[:12]
    _tasks[task_id] = {
        "id": task_id,
        "type": task_type.value,
        "status": TaskStatus.pending.value,
        "project_id": project_id,
        "object_id": object_id,
        "params": params or {},
        "result": None,
        "error": None,
        "retry_count": 0,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    # 清理超限任务
    if len(_tasks) > MAX_TASKS:
        oldest = sorted(_tasks.keys(), key=lambda k: _tasks[k]["created_at"])
        for k in oldest[:100]:
            del _tasks[k]
    logger.info("task_center: created %s type=%s", task_id, task_type.value)
    return task_id


def update_task(task_id: str, status: TaskStatus, result: Any = None, error: str | None = None):
    """更新任务状态"""
    if task_id not in _tasks:
        return
    _tasks[task_id]["status"] = status.value
    _tasks[task_id]["updated_at"] = datetime.utcnow().isoformat()
    if result is not None:
        _tasks[task_id]["result"] = result
    if error is not None:
        _tasks[task_id]["error"] = error
    if status == TaskStatus.retrying:
        _tasks[task_id]["retry_count"] += 1


def get_task(task_id: str) -> dict | None:
    """获取任务详情"""
    return _tasks.get(task_id)


def list_tasks(
    project_id: str | None = None,
    task_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """列出任务（支持筛选）"""
    items = list(_tasks.values())
    if project_id:
        items = [t for t in items if t["project_id"] == project_id]
    if task_type:
        items = [t for t in items if t["type"] == task_type]
    if status:
        items = [t for t in items if t["status"] == status]
    items.sort(key=lambda t: t["created_at"], reverse=True)
    return items[:limit]


def get_stats(project_id: str | None = None) -> dict:
    """任务统计"""
    items = list(_tasks.values())
    if project_id:
        items = [t for t in items if t["project_id"] == project_id]
    total = len(items)
    by_status = {}
    for t in items:
        s = t["status"]
        by_status[s] = by_status.get(s, 0) + 1
    return {
        "total": total,
        "by_status": by_status,
        "failed_count": by_status.get("failed", 0),
        "processing_count": by_status.get("processing", 0),
    }


def retry_task(task_id: str) -> dict | None:
    """人工重试失败任务 — 将状态改为 retrying，由调用方重新执行"""
    task = _tasks.get(task_id)
    if not task:
        return None
    if task["status"] not in ("failed",):
        return {"error": f"只有 failed 状态的任务可以重试，当前状态: {task['status']}"}
    task["status"] = TaskStatus.retrying.value
    task["retry_count"] += 1
    task["error"] = None
    task["updated_at"] = datetime.utcnow().isoformat()
    logger.info("task_center: retry %s type=%s retry_count=%d", task_id, task["type"], task["retry_count"])
    return task
