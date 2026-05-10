# -*- coding: utf-8 -*-
"""导入队列服务 — 并发控制 + 进度跟踪

多用户同时导入时：
1. 同一项目同一时间只允许一个导入任务
2. 不同项目可以并行导入（但总并发数有上限）
3. 导入进度实时推送（SSE）
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.models.audit_platform_models import ImportBatch, ImportStatus
from app.models.dataset_models import ImportJob, JobStatus

logger = logging.getLogger(__name__)

# 全局导入锁（project_id -> 导入状态）
_import_locks: dict[str, dict] = {}
_MAX_CONCURRENT_IMPORTS = 3  # 最大并发导入数
_STALE_IMPORT_TIMEOUT = timedelta(minutes=30)  # 30分钟无进度视为卡死
IMPORT_JOB_DATA_TYPE = "__smart_import_job__"

# asyncio 互斥锁：保证 acquire_lock 的检查+写入原子性（单 worker 内有效）
_acquire_mutex = asyncio.Lock()


class ImportLockError(RuntimeError):
    """无法获取项目导入锁（F23）。

    场景：activate 和 rollback 互斥；rollback 请求时检测到同项目已有
    activate/import/rollback 在进行，抛出此异常让路由层转 409。
    """

    def __init__(self, message: str, *, project_id: UUID | str | None = None, action: str | None = None):
        super().__init__(message)
        self.project_id = str(project_id) if project_id else None
        self.action = action


class ImportQueueService:
    """导入队列管理"""

    @staticmethod
    def _cleanup_stale_memory_locks():
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None).replace(tzinfo=None) - _STALE_IMPORT_TIMEOUT
        stale_projects: list[str] = []
        for pid, info in _import_locks.items():
            started = info.get("started")
            if not started:
                continue
            try:
                started_at = datetime.fromisoformat(started)
            except ValueError:
                continue
            if started_at < cutoff:
                stale_projects.append(pid)
        for pid in stale_projects:
            _import_locks.pop(pid, None)

    @staticmethod
    async def _expire_stale_jobs(db: AsyncSession):
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None).replace(tzinfo=None) - _STALE_IMPORT_TIMEOUT
        result = await db.execute(
            select(ImportBatch).where(
                ImportBatch.data_type == IMPORT_JOB_DATA_TYPE,
                ImportBatch.status == ImportStatus.processing,
                ImportBatch.started_at.is_not(None),
                ImportBatch.started_at < cutoff,
            )
        )
        stale_batches = result.scalars().all()
        if not stale_batches:
            return

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for batch in stale_batches:
            summary = dict(batch.validation_summary or {})
            summary.update({
                "job": True,
                "progress": -1,
                "message": "导入任务已失效，请重新发起导入",
                "error": "导入任务已失效，请重新发起导入",
            })
            batch.status = ImportStatus.failed
            batch.completed_at = now
            batch.validation_summary = summary
            _import_locks.pop(str(batch.project_id), None)
        await db.commit()

    @staticmethod
    async def _get_active_job_batch(project_id: UUID, db: AsyncSession) -> ImportBatch | None:
        result = await db.execute(
            select(ImportBatch)
            .where(
                ImportBatch.project_id == project_id,
                ImportBatch.data_type == IMPORT_JOB_DATA_TYPE,
                ImportBatch.status == ImportStatus.processing,
            )
            .order_by(ImportBatch.created_at.desc())
        )
        return result.scalars().first()

    @staticmethod
    async def _get_latest_job_batch(project_id: UUID, db: AsyncSession) -> ImportBatch | None:
        result = await db.execute(
            select(ImportBatch)
            .where(
                ImportBatch.project_id == project_id,
                ImportBatch.data_type == IMPORT_JOB_DATA_TYPE,
            )
            .order_by(ImportBatch.created_at.desc())
        )
        return result.scalars().first()

    @staticmethod
    async def _count_active_jobs(db: AsyncSession) -> int:
        result = await db.execute(
            select(func.count())
            .select_from(ImportBatch)
            .where(
                ImportBatch.data_type == IMPORT_JOB_DATA_TYPE,
                ImportBatch.status == ImportStatus.processing,
            )
        )
        return int(result.scalar_one() or 0)

    @staticmethod
    def _build_status_payload(batch_id: UUID | str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "batch_id": str(batch_id),
            "status": payload.get("status", ImportStatus.processing.value),
            "message": payload.get("message", ""),
            "progress": payload.get("progress", 0),
            "result": payload.get("result"),
            "started": payload.get("started"),
            "user": payload.get("user"),
        }

    @staticmethod
    def _build_batch_payload(batch: ImportBatch) -> dict[str, Any]:
        summary = dict(batch.validation_summary or {})
        progress = summary.get("progress")
        if progress is None:
            if batch.status == ImportStatus.completed:
                progress = 100
            elif batch.status == ImportStatus.failed:
                progress = -1
            else:
                progress = 0
        message = summary.get("message") or summary.get("error") or ""
        return {
            "batch_id": str(batch.id),
            "status": batch.status.value,
            "message": message,
            "progress": progress,
            "result": summary.get("result"),
            "started": batch.started_at.isoformat() if batch.started_at else None,
            "user": summary.get("user"),
        }

    @staticmethod
    def _build_import_job_payload(job: ImportJob) -> dict[str, Any]:
        progress = int(job.progress_pct or 0)
        if job.status in (JobStatus.failed, JobStatus.timed_out, JobStatus.canceled):
            progress = -1
        elif job.status == JobStatus.completed:
            progress = 100
        message = job.progress_message or job.error_message or ""
        return {
            "job_id": str(job.id),
            "status": job.status.value,
            "message": message,
            "progress": progress,
            "result": job.result_summary,
            "started": job.started_at.isoformat() if job.started_at else None,
        }

    @staticmethod
    async def _update_job_batch(
        batch_id: UUID,
        db: AsyncSession,
        *,
        status: ImportStatus,
        progress: int,
        message: str,
        result: dict | None = None,
        year: int | None = None,
        record_count: int | None = None,
    ):
        batch = await db.get(ImportBatch, batch_id)
        if batch is None:
            return

        summary = dict(batch.validation_summary or {})
        summary.update({
            "job": True,
            "progress": progress,
            "message": message,
        })
        if result is not None:
            summary["result"] = result
        if status == ImportStatus.failed:
            summary["error"] = message

        batch.status = status
        batch.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        batch.validation_summary = summary
        if year is not None and year > 0:
            batch.year = year
        if record_count is not None:
            batch.record_count = record_count
        await db.commit()

    @staticmethod
    async def persist_progress(
        batch_id: UUID,
        *,
        progress: int,
        message: str,
        result: dict | None = None,
    ):
        try:
            async with async_session() as db:
                batch = await db.get(ImportBatch, batch_id)
                if batch is None or batch.status != ImportStatus.processing:
                    return

                summary = dict(batch.validation_summary or {})
                if (
                    summary.get("progress") == progress
                    and summary.get("message") == message
                    and (result is None or summary.get("result") == result)
                ):
                    return

                summary.update({
                    "job": True,
                    "progress": progress,
                    "message": message,
                })
                if result is not None:
                    summary["result"] = result
                batch.validation_summary = summary
                await db.commit()
        except Exception:
            logger.exception("持久化导入进度失败: batch_id=%s progress=%s", batch_id, progress)

    @staticmethod
    async def acquire_lock(
        project_id: UUID,
        user_id: str,
        db: AsyncSession,
        *,
        source_type: str,
        file_name: str,
        year: int = 0,
    ) -> tuple[bool, str, UUID | None]:
        """尝试获取导入锁。

        数据库唯一索引保证跨实例互斥；asyncio.Lock 仅减少单进程内重复提交竞争。

        Returns:
            (success, message, batch_id)
        """
        async with _acquire_mutex:
            pid = str(project_id)
            ImportQueueService._cleanup_stale_memory_locks()
            await ImportQueueService._expire_stale_jobs(db)

            # 检查数据库中是否有活跃任务（跨 Web/worker 实例唯一可信来源）
            active_batch = await ImportQueueService._get_active_job_batch(project_id, db)
            if active_batch is not None:
                started = active_batch.started_at.isoformat() if active_batch.started_at else "?"
                return False, f"项目正在导入中（{started} 开始）", None

            # 检查总并发数
            active = await ImportQueueService._count_active_jobs(db)
            if active >= _MAX_CONCURRENT_IMPORTS:
                return False, f"系统繁忙，当前有 {active} 个导入任务在执行，请稍后重试", None

            started_at = datetime.now(timezone.utc).replace(tzinfo=None)
            batch = ImportBatch(
                project_id=project_id,
                year=year,
                source_type=source_type,
                file_name=file_name,
                data_type=IMPORT_JOB_DATA_TYPE,
                status=ImportStatus.processing,
                started_at=started_at,
                validation_summary={
                    "job": True,
                    "progress": 0,
                    "message": "导入任务已创建",
                    "user": user_id,
                },
            )
            db.add(batch)
            try:
                await db.commit()
                await db.refresh(batch)
            except IntegrityError:
                await db.rollback()
                active_batch = await ImportQueueService._get_active_job_batch(project_id, db)
                started = active_batch.started_at.isoformat() if active_batch and active_batch.started_at else "?"
                return False, f"项目正在导入中（{started} 开始）", None

            _import_locks[pid] = {
                "batch_id": str(batch.id),
                "user": user_id,
                "started": started_at.isoformat(),
                "progress": 0,
                "status": ImportStatus.processing.value,
                "message": "导入任务已创建",
            }
            return True, "OK", batch.id

    @staticmethod
    def release_lock(project_id: UUID):
        """释放导入锁。"""
        _import_locks.pop(str(project_id), None)

    # -----------------------------------------------------------------------
    # F23 / Sprint 5.14: activate / rollback 轻量级项目锁
    # -----------------------------------------------------------------------
    # 与 `acquire_lock`（创建 ImportBatch 的完整导入锁）不同，本组 API 只写
    # `_import_locks` 内存态，专用于 DatasetService.activate / rollback 的
    # 短时互斥（典型耗时 < 1 秒，B' 架构后）。两者共享同一 `_import_locks`
    # 字典，所以：
    #   - 有 import 在跑 → try_acquire_action_lock 失败（rollback 拒绝）
    #   - 有 rollback 在跑 → acquire_lock 能检测到 _import_locks 但
    #     数据库层无 ImportBatch，此处不做硬阻断（设计文档 D8.4 只要求
    #     rollback 自身互斥，不要求 rollback 在跑时 import 也拒绝）

    @staticmethod
    def try_acquire_action_lock(
        project_id: UUID,
        *,
        action: str,
        user_id: str | None = None,
    ) -> bool:
        """尝试获取 activate / rollback 的轻量级项目锁。

        Returns:
            True  — 成功获取，调用方必须在 finally 中调用 release_action_lock
            False — 已被占用，调用方应抛 ImportLockError
        """
        pid = str(project_id)
        if pid in _import_locks:
            return False
        _import_locks[pid] = {
            "action": action,
            "user": user_id,
            "started": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            "batch_id": None,  # 非完整导入，无 ImportBatch
            "status": "processing",
            "progress": 0,
            "message": f"{action} 进行中",
        }
        return True

    @staticmethod
    def release_action_lock(project_id: UUID) -> None:
        """释放 activate / rollback 的轻量级项目锁。"""
        _import_locks.pop(str(project_id), None)

    # -----------------------------------------------------------------------
    # F21 / Sprint 5.6: 锁透明 —— 查询当前项目的锁详情
    # -----------------------------------------------------------------------

    @staticmethod
    async def get_lock_info(
        project_id: UUID, db: AsyncSession
    ) -> dict | None:
        """F21: 返回当前项目的导入锁详情（holder / 进度 / 预估剩余）。

        优先查 ImportJob（完整导入场景），降级查 `_import_locks`
        内存态（rollback/activate 等短操作）。无锁返回 None。

        返回结构对应前端 LockInfo（has_lock / action / holder_* /
        current_phase / progress_pct / rows_processed /
        estimated_remaining_seconds / acquired_at / progress_message）。
        """
        from app.models.core import User  # 延迟 import 避免循环依赖

        pid = str(project_id)
        state = _import_locks.get(pid)

        # 1) 先找活跃 ImportJob（导入场景 holder 最权威）
        active_statuses = (
            JobStatus.pending,
            JobStatus.queued,
            JobStatus.running,
            JobStatus.validating,
            JobStatus.writing,
            JobStatus.activating,
        )
        result = await db.execute(
            select(ImportJob)
            .where(
                ImportJob.project_id == project_id,
                ImportJob.status.in_(active_statuses),
            )
            .order_by(ImportJob.created_at.desc())
            .limit(1)
        )
        job = result.scalar_one_or_none()

        if job:
            holder_name = await _resolve_holder_name(db, job.created_by)

            # 预估剩余耗时（基于已用时间线性外推）
            estimated_remaining = None
            if job.started_at and job.progress_pct and 5 <= job.progress_pct < 100:
                started = (
                    job.started_at.replace(tzinfo=None)
                    if job.started_at.tzinfo
                    else job.started_at
                )
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                elapsed_sec = max(1, int((now - started).total_seconds()))
                total_est = elapsed_sec * 100 / job.progress_pct
                estimated_remaining = max(0, int(total_est - elapsed_sec))

            rows_processed = 0
            if job.result_summary and isinstance(job.result_summary, dict):
                rows_processed = int(job.result_summary.get("total_parsed", 0) or 0)

            return {
                "has_lock": True,
                "action": "import",
                "holder_user_id": str(job.created_by) if job.created_by else None,
                "holder_name": holder_name,
                "job_id": str(job.id),
                "current_phase": job.current_phase or "writing",
                "current_phase_cn": _phase_cn(job.current_phase),
                "progress_pct": job.progress_pct or 0,
                "rows_processed": rows_processed,
                "estimated_remaining_seconds": estimated_remaining,
                "acquired_at": (
                    job.started_at.isoformat() if job.started_at else None
                ),
                "progress_message": job.progress_message,
            }

        # 2) 没有活跃 ImportJob → 查内存态 action_lock（rollback/activate 短操作）
        if state:
            user_id_str = state.get("user")
            holder_name = None
            if user_id_str:
                try:
                    holder_uuid = UUID(str(user_id_str))
                    holder_name = await _resolve_holder_name(db, holder_uuid)
                except (ValueError, TypeError):
                    pass

            return {
                "has_lock": True,
                "action": state.get("action", "import"),
                "holder_user_id": user_id_str,
                "holder_name": holder_name,
                "job_id": None,
                "current_phase": state.get("status", "processing"),
                "current_phase_cn": _phase_cn(state.get("status")),
                "progress_pct": state.get("progress", 0),
                "rows_processed": 0,
                "estimated_remaining_seconds": None,
                "acquired_at": state.get("started"),
                "progress_message": state.get("message"),
            }

        return None

    @staticmethod
    async def force_release(
        project_id: UUID,
        db: AsyncSession,
        *,
        job_id: UUID | None = None,
        force: bool = False,
    ) -> str:
        """强制释放导入锁。

        - 提供 job_id 时：精确取消指定作业，并清理其关联 queue batch。
        - 不提供 job_id 时：仅在 force=True 下执行项目级清理。
        """
        if job_id is not None:
            from app.services.import_job_service import ImportJobService
            from app.services.import_job_runner import ImportJobRunner

            job = await ImportJobService.get_job(db, job_id)
            if job is None or job.project_id != project_id:
                return "未找到指定作业，未执行重置"

            prev_status = job.status
            canceled = False
            try:
                await ImportJobService.cancel(db, job_id)
                canceled = True
            except ValueError:
                # 已终态或不可取消时不强制改状态，但仍尝试释放残留锁。
                pass

            ImportJobRunner.request_cancel(job_id)
            ImportQueueService.release_lock(project_id)

            batch_id_raw = (job.options or {}).get("queue_batch_id")
            if batch_id_raw:
                try:
                    batch_id = UUID(str(batch_id_raw))
                    batch = await db.get(ImportBatch, batch_id)
                    if (
                        batch is not None
                        and batch.project_id == project_id
                        and batch.data_type == IMPORT_JOB_DATA_TYPE
                        and batch.status == ImportStatus.processing
                    ):
                        summary = dict(batch.validation_summary or {})
                        summary.update({"job": True, "progress": -1, "message": "导入被手动重置", "error": "导入被手动重置"})
                        batch.status = ImportStatus.failed
                        batch.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                        batch.validation_summary = summary
                except Exception:
                    logger.warning("force_release(job_id) 更新 batch 失败: %s", batch_id_raw)

            await db.commit()
            if canceled:
                return f"已重置作业 {job_id}（{prev_status.value} → canceled）"
            return f"已清理作业 {job_id} 的残留锁（当前状态: {prev_status.value}）"

        if not force:
            return "未提供 job_id，已拒绝项目级重置（如需继续请显式 force=true）"

        pid = str(project_id)
        _import_locks.pop(pid, None)

        # 将该项目所有 processing 状态的 job batch 标记为 failed
        result = await db.execute(
            select(ImportBatch).where(
                ImportBatch.project_id == project_id,
                ImportBatch.data_type == IMPORT_JOB_DATA_TYPE,
                ImportBatch.status == ImportStatus.processing,
            )
        )
        stale_batches = result.scalars().all()
        for batch in stale_batches:
            batch.status = ImportStatus.failed
            batch.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            if batch.validation_summary and isinstance(batch.validation_summary, dict):
                batch.validation_summary["error"] = "导入被中断，已自动清理"
            else:
                batch.validation_summary = {"error": "导入被中断，已自动清理"}
        if stale_batches:
            await db.commit()
        return f"已释放锁，清理 {len(stale_batches)} 个卡住的任务"

    @staticmethod
    def update_progress(project_id: UUID, progress: int, message: str = "", result: dict | None = None):
        """更新导入进度（0-100），可选存储最终结果。"""
        pid = str(project_id)
        if pid in _import_locks:
            _import_locks[pid]["progress"] = progress
            _import_locks[pid]["message"] = message
            if progress < 0:
                _import_locks[pid]["status"] = ImportStatus.failed.value
            elif progress >= 100:
                _import_locks[pid]["status"] = ImportStatus.completed.value
            else:
                _import_locks[pid]["status"] = ImportStatus.processing.value
            if result is not None:
                _import_locks[pid]["result"] = result
            batch_id = _import_locks[pid].get("batch_id")
            if batch_id and 0 <= progress < 100:
                asyncio.create_task(
                    ImportQueueService.persist_progress(
                        UUID(str(batch_id)),
                        progress=progress,
                        message=message,
                        result=result,
                    )
                )

    @staticmethod
    async def complete_job(
        project_id: UUID,
        batch_id: UUID,
        db: AsyncSession,
        *,
        message: str,
        result: dict | None = None,
        year: int | None = None,
        record_count: int | None = None,
    ):
        ImportQueueService.update_progress(project_id, 100, message, result=result)
        await ImportQueueService._update_job_batch(
            batch_id,
            db,
            status=ImportStatus.completed,
            progress=100,
            message=message,
            result=result,
            year=year,
            record_count=record_count,
        )
        ImportQueueService.release_lock(project_id)

    @staticmethod
    async def fail_job(
        project_id: UUID,
        batch_id: UUID,
        db: AsyncSession,
        *,
        message: str,
        result: dict | None = None,
        year: int | None = None,
    ):
        # 先释放内存锁
        ImportQueueService.update_progress(project_id, -1, message, result=result)
        ImportQueueService.release_lock(project_id)

        # rollback 当前事务（可能已 abort）
        try:
            await db.rollback()
        except Exception:
            pass

        # 用独立 session 更新 batch 状态（避免被 abort 的事务影响）
        try:
            async with async_session() as fresh_db:
                batch = await fresh_db.get(ImportBatch, batch_id)
                if batch:
                    summary = dict(batch.validation_summary or {})
                    summary.update({"job": True, "progress": -1, "message": message, "error": message})
                    if result is not None:
                        summary["result"] = result
                    batch.status = ImportStatus.failed
                    batch.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    batch.validation_summary = summary
                    if year is not None and year > 0:
                        batch.year = year
                    await fresh_db.commit()
        except Exception as e:
            logger.warning("fail_job 更新 batch 失败: %s", e)

    @staticmethod
    async def get_status(project_id: UUID, db: AsyncSession) -> Optional[dict]:
        """获取导入状态。"""
        latest_job_result = await db.execute(
            select(ImportJob)
            .where(ImportJob.project_id == project_id)
            .order_by(ImportJob.created_at.desc())
        )
        latest_job = latest_job_result.scalars().first()
        if latest_job is not None:
            return ImportQueueService._build_import_job_payload(latest_job)

        pid = str(project_id)
        state = _import_locks.get(pid)
        if state is not None:
            return ImportQueueService._build_status_payload(
                state.get("batch_id", ""),
                state,
            )

        await ImportQueueService._expire_stale_jobs(db)
        batch = await ImportQueueService._get_latest_job_batch(project_id, db)
        if batch is None:
            return None
        return ImportQueueService._build_batch_payload(batch)

    @staticmethod
    async def get_all_active(db: AsyncSession) -> list[dict]:
        """获取所有活跃的导入任务。"""
        active_jobs_result = await db.execute(
            select(ImportJob)
            .where(ImportJob.status.in_([
                JobStatus.pending,
                JobStatus.queued,
                JobStatus.running,
                JobStatus.validating,
                JobStatus.writing,
                JobStatus.activating,
            ]))
            .order_by(ImportJob.created_at.desc())
        )
        active_jobs = active_jobs_result.scalars().all()
        if active_jobs:
            return [
                {
                    "project_id": str(job.project_id),
                    **ImportQueueService._build_import_job_payload(job),
                }
                for job in active_jobs
            ]

        await ImportQueueService._expire_stale_jobs(db)
        result = await db.execute(
            select(ImportBatch)
            .where(
                ImportBatch.data_type == IMPORT_JOB_DATA_TYPE,
                ImportBatch.status == ImportStatus.processing,
            )
            .order_by(ImportBatch.created_at.desc())
        )
        active_batches = result.scalars().all()
        active_map: dict[str, dict[str, Any]] = {}
        for batch in active_batches:
            pid = str(batch.project_id)
            if pid in _import_locks:
                active_map[pid] = {
                    "project_id": pid,
                    **ImportQueueService._build_status_payload(
                        _import_locks[pid].get("batch_id", batch.id),
                        _import_locks[pid],
                    ),
                }
            else:
                active_map[pid] = {
                    "project_id": pid,
                    **ImportQueueService._build_batch_payload(batch),
                }
        return list(active_map.values())


# ---------------------------------------------------------------------------
# F21 / Sprint 5.6: 模块级辅助函数
# ---------------------------------------------------------------------------

_PHASE_CN_MAPPING = {
    "pending": "排队中",
    "queued": "排队中",
    "running": "运行中",
    "validating": "校验中",
    "writing": "写入中",
    "activating": "激活中",
    "activate_dataset_done": "激活完成",
    "rebuild_aux_summary_done": "收尾中",
    "rollback": "回滚中",
    "activate": "激活中",
    "import": "导入中",
    "processing": "处理中",
    "completed": "已完成",
    "failed": "已失败",
    "canceled": "已取消",
}


def _phase_cn(phase: str | None) -> str:
    """阶段英文名 → 中文展示（F21 锁透明 tooltip 用）。"""
    if not phase:
        return ""
    return _PHASE_CN_MAPPING.get(phase, phase)


async def _resolve_holder_name(
    db: AsyncSession, user_id: UUID | None
) -> str | None:
    """根据 user_id 查询用户名；用户不存在或查询失败时返回 None。"""
    if not user_id:
        return None
    try:
        from app.models.core import User  # 延迟 import
        result = await db.execute(select(User.username).where(User.id == user_id))
        row = result.first()
        if row:
            return row[0]
    except Exception:
        logger.debug("get_lock_info: 解析 holder_name 失败", exc_info=True)
    return None
