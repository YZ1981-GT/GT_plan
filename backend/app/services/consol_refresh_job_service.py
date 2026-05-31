"""合并模块一键级联刷新 — 后台 job 注册表 + worker（consol-phase2-orchestration Task 2）

需求 2（A5）：一键级联刷新走**后台 worker**（不在请求线程跑全量重算，关联 R1），
SSE 推进度（不轮询打爆 asyncpg pool，关联 R5），job 状态可 GET 兜底查询
（SSE 断开可查，关联 EH6），worker 异常置 failed + SSE error（关联 EH2）。

设计取舍（ADR 倾向「轻量内存 + SSE」，Task 0 复用基础设施核实）：
    job 状态用**进程内内存注册表** `_JOBS`（非 import_job 表）。理由：
    - refresh-all 是「触发即跑、进度经 SSE 推、断线可 GET 兜底」的短时编排任务，
      不需要 ledger 那种重型可恢复 job 表（持久化/重启续跑）。
    - 内存注册表 + SSE 进度 + GET 兜底已满足需求 2.1~2.4 全部验收。
    - 进程重启后 job 丢失属可接受（前端重新触发即可），不引入额外表/迁移。

连接铁律（R5，呼应 memory「SSE 不占 asyncpg pool」教训）：
    - worker 用**自己的 db session**（`async_session_factory()`），绝不复用请求 session
      （请求在返回 job_id 后即结束，其 session 已关闭）。
    - 进度推送走 `event_bus.broadcast_raw`（内存 SSE 队列 fan-out + Redis Stream 持久化），
      **不持有数据库连接**——SSE 消费端（events.py `/stream`）也不占 asyncpg。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.core.database import async_session as async_session_factory
from app.services.consol_cascade_refresh_service import TOTAL_STEPS, refresh_all
from app.services.event_bus import event_bus

logger = logging.getLogger(__name__)

# SSE 事件类型（前端订阅 events.py `/stream` 过滤 project_id/year 后渲染进度条）
SSE_PROGRESS = "consol.refresh.progress"
SSE_COMPLETED = "consol.refresh.completed"
SSE_ERROR = "consol.refresh.error"

# job 状态机
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

# 进程内 job 注册表（轻量内存，非 DB 表）
_JOBS: dict[str, "RefreshJob"] = {}

# 持有后台 task 强引用，避免 asyncio.create_task 的 task 被 GC 回收（已知陷阱）
_BACKGROUND_TASKS: set[asyncio.Task] = set()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RefreshJob:
    """一键级联刷新 job 状态（进程内内存，GET 兜底查询用）。"""

    job_id: str
    project_id: str
    year: int
    status: str = STATUS_QUEUED
    current_step: str | None = None
    steps_completed: list[str] = field(default_factory=list)
    total_steps: int = TOTAL_STEPS
    errors: list[dict] = field(default_factory=list)
    result: dict | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)


def create_job(project_id: UUID | str, year: int) -> RefreshJob:
    """创建一个 queued 状态的刷新 job 并登记到注册表。"""
    job_id = str(uuid4())
    job = RefreshJob(job_id=job_id, project_id=str(project_id), year=year)
    _JOBS[job_id] = job
    logger.info("合并一键刷新 job 创建：job_id=%s 项目=%s 年度=%s", job_id, project_id, year)
    return job


def get_job(job_id: str) -> RefreshJob | None:
    """按 job_id 查询 job 状态（SSE 断开后的 GET 兜底，EH6）。"""
    return _JOBS.get(job_id)


def schedule_refresh_job(project_id: UUID | str, year: int) -> RefreshJob:
    """创建 job 并调度后台 worker（不在请求线程跑，R1）。

    用 asyncio.create_task 调度，使 worker 在 HTTP 响应返回 job_id 后继续存活；
    task 引用存入模块级集合避免被 GC 回收。
    """
    job = create_job(project_id, year)
    task = asyncio.create_task(run_refresh_job(job.job_id, str(project_id), year))
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return job


async def run_refresh_job(job_id: str, project_id: str, year: int) -> None:
    """后台 worker：跑 refresh_all 并经 SSE 推进度（A5，不占请求连接）。

    - 用自己的 db session（绝不复用请求 session，请求已结束 session 已关闭）。
    - progress_cb 经 event_bus.broadcast_raw 推 SSE + 同步更新内存 job 状态。
    - worker 整体异常（如建会话失败）→ job=failed + SSE error（EH2）。
    """
    job = _JOBS.get(job_id)
    if job is None:
        logger.warning("合并一键刷新 worker 启动时 job 已不存在：job_id=%s", job_id)
        return

    job.status = STATUS_RUNNING
    job.updated_at = _now()

    def publish_sse(
        step: str,
        current: int,
        total: int,
        current_node: str | None,
        status: str,
    ) -> None:
        """进度回调：更新内存 job 状态 + 广播 SSE 进度事件（不占 asyncpg pool）。"""
        job.current_step = step
        job.total_steps = total
        if status == "completed" and step not in job.steps_completed:
            job.steps_completed.append(step)
        job.updated_at = _now()
        event_bus.broadcast_raw(
            SSE_PROGRESS,
            {
                "project_id": project_id,
                "year": year,
                "job_id": job_id,
                "step": step,
                "current": current,
                "total": total,
                "current_node": current_node,
                "status": status,
            },
        )

    try:
        async with async_session_factory() as db:
            result = await refresh_all(
                db,
                UUID(project_id),
                year,
                progress_cb=publish_sse,
            )

        # refresh_all 内部已做每步失败隔离，正常返回即视为编排完成（可能部分成功）。
        recon = None
        if result.reconciliation is not None:
            recon = {
                "is_reconciled": result.reconciliation.is_reconciled,
                "diff_count": len(result.reconciliation.diffs),
                "max_abs_diff": str(result.reconciliation.max_abs_diff),
            }
        job.status = STATUS_COMPLETED
        job.steps_completed = list(result.steps_completed)
        job.errors = list(result.errors)
        job.result = {
            "nodes_refreshed": result.nodes_refreshed,
            "steps_completed": list(result.steps_completed),
            "errors": list(result.errors),
            "duration_ms": result.duration_ms,
            "reconciliation": recon,
        }
        job.updated_at = _now()
        event_bus.broadcast_raw(
            SSE_COMPLETED,
            {
                "project_id": project_id,
                "year": year,
                "job_id": job_id,
                "status": STATUS_COMPLETED,
                "nodes_refreshed": result.nodes_refreshed,
                "steps_completed": list(result.steps_completed),
                "errors": list(result.errors),
                "duration_ms": result.duration_ms,
            },
        )
        logger.info(
            "合并一键刷新 job 完成：job_id=%s 步骤=%s 错误=%d 耗时=%dms",
            job_id, result.steps_completed, len(result.errors), result.duration_ms,
        )
    except Exception as exc:  # noqa: BLE001 - worker 整体异常隔离（EH2）
        job.status = STATUS_FAILED
        job.errors.append({"step": job.current_step, "node": None, "error": str(exc)})
        job.updated_at = _now()
        logger.exception("合并一键刷新 worker 异常，job 置 failed：job_id=%s", job_id)
        event_bus.broadcast_raw(
            SSE_ERROR,
            {
                "project_id": project_id,
                "year": year,
                "job_id": job_id,
                "status": STATUS_FAILED,
                "error": str(exc),
            },
        )
