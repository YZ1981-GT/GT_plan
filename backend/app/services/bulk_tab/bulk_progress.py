"""批量导入导出 SSE 进度服务 — workpaper-bulk-tab-import-export

内存维护任务进度 + SSE 推送：
- create_task → 注册任务，返回 task_id
- tick / complete / fail → 更新进度并广播到 SSE 订阅队列
- subscribe → 返回 asyncio.Queue 供 SSE 端点消费

复用模式：chain_workflow.py 的 subscriber queue + export_progress_service 的内存任务状态。

Validates: Requirements 6.1
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class BulkTaskProgress:
    """批量任务进度状态"""

    task_id: str
    project_id: str
    user_id: str
    operation: str  # "export-templates" | "export-data" | "import"
    total: int
    current: int = 0
    status: str = "pending"  # pending / running / complete / failed
    message: str = ""
    error: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    # 异步导出结果：ZIP 文件磁盘路径（供 GET /export/{task_id}/download）
    result_path: Optional[str] = None
    result_filename: Optional[str] = None
    # 异步导入结果：ImportReport.to_dict()（供 GET /import/{task_id}/result）
    result: Optional[dict[str, Any]] = None


class BulkProgressService:
    """批量导入导出进度管理器 — 内存状态 + SSE subscriber queue 推送"""

    def __init__(self) -> None:
        self._tasks: dict[str, BulkTaskProgress] = {}
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    # ------------------------------------------------------------------
    # 任务生命周期
    # ------------------------------------------------------------------

    def create_task(
        self,
        project_id: str,
        user_id: str,
        operation: str,
        total: int,
    ) -> BulkTaskProgress:
        """创建进度追踪任务，返回 task 对象。"""
        task_id = str(uuid.uuid4())
        task = BulkTaskProgress(
            task_id=task_id,
            project_id=project_id,
            user_id=user_id,
            operation=operation,
            total=total,
        )
        self._tasks[task_id] = task
        task.status = "running"
        return task

    def get_task(self, task_id: str) -> Optional[BulkTaskProgress]:
        return self._tasks.get(task_id)

    def set_total(self, task_id: str, total: int) -> None:
        """任务真实条目数已知后回填 total（异步 export/import 场景）。"""
        task = self._tasks.get(task_id)
        if task:
            task.total = max(0, int(total))

    def set_result_path(
        self, task_id: str, path: str, filename: str | None = None
    ) -> None:
        """记录异步导出的 ZIP 磁盘路径 + 下载文件名。"""
        task = self._tasks.get(task_id)
        if task:
            task.result_path = path
            task.result_filename = filename

    def set_result(self, task_id: str, result: dict[str, Any]) -> None:
        """记录异步导入的 ImportReport（供完成后 GET 查询）。"""
        task = self._tasks.get(task_id)
        if task:
            task.result = result

    # ------------------------------------------------------------------
    # 进度更新（由 BulkExport/Import Service 的 progress 回调调用）
    # ------------------------------------------------------------------

    def tick(self, task_id: str, message: str = "") -> None:
        """推进一步进度并广播 SSE 事件。"""
        task = self._tasks.get(task_id)
        if not task:
            return
        task.current += 1
        task.message = message
        self._broadcast(task_id, {
            "type": "progress",
            "current": task.current,
            "total": task.total,
            "message": message,
        })

    def complete(self, task_id: str, message: str = "完成") -> None:
        """标记任务完成并广播终态。"""
        task = self._tasks.get(task_id)
        if not task:
            return
        task.status = "complete"
        task.message = message
        task.completed_at = datetime.now(timezone.utc)
        self._broadcast(task_id, {
            "type": "complete",
            "current": task.current,
            "total": task.total,
            "message": message,
        })

    def fail(self, task_id: str, error: str) -> None:
        """标记任务失败并广播终态。"""
        task = self._tasks.get(task_id)
        if not task:
            return
        task.status = "failed"
        task.error = error
        task.completed_at = datetime.now(timezone.utc)
        self._broadcast(task_id, {
            "type": "error",
            "current": task.current,
            "total": task.total,
            "message": error,
        })

    # ------------------------------------------------------------------
    # SSE subscriber 管理
    # ------------------------------------------------------------------

    def subscribe(self, task_id: str) -> asyncio.Queue:
        """为 SSE 端点创建订阅队列。"""
        if task_id not in self._subscribers:
            self._subscribers[task_id] = []
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers[task_id].append(queue)
        return queue

    def unsubscribe(self, task_id: str, queue: asyncio.Queue) -> None:
        """移除订阅队列。"""
        queues = self._subscribers.get(task_id, [])
        if queue in queues:
            queues.remove(queue)
        if not queues:
            self._subscribers.pop(task_id, None)

    # ------------------------------------------------------------------
    # 内部广播
    # ------------------------------------------------------------------

    def _broadcast(self, task_id: str, data: dict[str, Any]) -> None:
        """向所有该 task 的订阅者推送事件。"""
        queues = self._subscribers.get(task_id, [])
        for q in queues:
            try:
                q.put_nowait(data)
            except asyncio.QueueFull:
                pass  # 消费者太慢则丢弃

    # ------------------------------------------------------------------
    # 适配器：给 BulkExport/Import Service 的 progress 回调
    # ------------------------------------------------------------------

    def make_progress_callback(self, task_id: str) -> "BulkProgressCallback":
        """创建给服务层的 progress 回调适配器。"""
        return BulkProgressCallback(self, task_id)

    # ------------------------------------------------------------------
    # 清理过期任务（24h）
    # ------------------------------------------------------------------

    def cleanup_expired(self, max_age_hours: float = 24.0) -> int:
        """清理超过 max_age_hours 的内存任务记录。"""
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=max_age_hours)
        removed = 0
        for task_id, task in list(self._tasks.items()):
            ref_time = task.completed_at or task.created_at
            if ref_time and ref_time < cutoff:
                self._tasks.pop(task_id, None)
                self._subscribers.pop(task_id, None)
                removed += 1
        return removed


class BulkProgressCallback:
    """给 BulkExport/Import Service 使用的进度回调对象。

    满足服务层 `progress.tick(message?)` 调用约定。
    """

    def __init__(self, service: BulkProgressService, task_id: str) -> None:
        self._service = service
        self._task_id = task_id

    def tick(self, message: str = "") -> None:
        self._service.tick(self._task_id, message)


# 全局单例
bulk_progress_service = BulkProgressService()
