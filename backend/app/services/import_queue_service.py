# -*- coding: utf-8 -*-
"""导入队列服务 — 并发控制 + 进度跟踪

多用户同时导入时：
1. 同一项目同一时间只允许一个导入任务
2. 不同项目可以并行导入（但总并发数有上限）
3. 导入进度实时推送（SSE）
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

logger = logging.getLogger(__name__)

# 全局导入锁（project_id -> 导入状态）
_import_locks: dict[str, dict] = {}
_MAX_CONCURRENT_IMPORTS = 3  # 最大并发导入数


class ImportQueueService:
    """导入队列管理"""

    @staticmethod
    def acquire_lock(project_id: UUID, user_id: str = "") -> tuple[bool, str]:
        """尝试获取导入锁。

        Returns:
            (success, message)
        """
        pid = str(project_id)

        # 检查该项目是否已有导入在进行
        if pid in _import_locks:
            lock = _import_locks[pid]
            return False, f"项目正在导入中（{lock.get('user', '?')} 于 {lock.get('started', '?')} 开始）"

        # 检查总并发数
        active = len(_import_locks)
        if active >= _MAX_CONCURRENT_IMPORTS:
            return False, f"系统繁忙，当前有 {active} 个导入任务在执行，请稍后重试"

        _import_locks[pid] = {
            "user": user_id,
            "started": datetime.utcnow().isoformat(),
            "progress": 0,
            "status": "processing",
        }
        return True, "OK"

    @staticmethod
    def release_lock(project_id: UUID):
        """释放导入锁。"""
        _import_locks.pop(str(project_id), None)

    @staticmethod
    def update_progress(project_id: UUID, progress: int, message: str = ""):
        """更新导入进度（0-100）。"""
        pid = str(project_id)
        if pid in _import_locks:
            _import_locks[pid]["progress"] = progress
            _import_locks[pid]["message"] = message

    @staticmethod
    def get_status(project_id: UUID) -> Optional[dict]:
        """获取导入状态。"""
        return _import_locks.get(str(project_id))

    @staticmethod
    def get_all_active() -> list[dict]:
        """获取所有活跃的导入任务。"""
        return [
            {"project_id": pid, **info}
            for pid, info in _import_locks.items()
        ]
