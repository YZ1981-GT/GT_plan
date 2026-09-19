"""Materialize job 轻量登记表（Task 4 / 需求 2.8）

delegation preview 需要未物化行时，先提交**可追踪**的前置 materialize job；job 成功后
客户端重新请求 preview。expand 阶段用进程内登记表承载短生命周期 job 状态与结果：

- 状态机：``pending → running → succeeded | failed``。
- ``job failure 不产生 preview``：失败 job 的 ``result`` 为 None、``preview_allowed=False``。
- 线程/协程安全由 asyncio.Lock 保证；job 短暂且幂等，进程级足够（Task 8 接 preview 时复用）。

不引入新 DB 表（V105 无 job 表）；持久化 job 编排属后续任务范围。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class MaterializeJob:
    id: str
    project_id: str
    wp_index_ids: list[str]
    status: str = "pending"  # pending | running | succeeded | failed
    result: dict | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def preview_allowed(self) -> bool:
        """只有成功 job 才允许生成可消费 preview（Req 2.8）。"""
        return self.status == "succeeded"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["preview_allowed"] = self.preview_allowed
        return data


class _MaterializeJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, MaterializeJob] = {}
        self._lock = asyncio.Lock()

    async def create(self, project_id: str, wp_index_ids: list[str]) -> MaterializeJob:
        job = MaterializeJob(
            id=str(uuid.uuid4()),
            project_id=project_id,
            wp_index_ids=list(wp_index_ids),
        )
        async with self._lock:
            self._jobs[job.id] = job
        return job

    async def mark(
        self,
        job_id: str,
        status: str,
        *,
        result: dict | None = None,
        error: str | None = None,
    ) -> MaterializeJob | None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job.status = status
            if result is not None:
                job.result = result
            if error is not None:
                job.error = error
            job.updated_at = time.time()
            return job

    async def get(self, job_id: str, project_id: str | None = None) -> MaterializeJob | None:
        async with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            return None
        if project_id is not None and job.project_id != project_id:
            return None
        return job


# 进程级单例。
materialize_job_store = _MaterializeJobStore()
