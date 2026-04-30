"""导入作业服务 — Durable Job 状态机

将导入任务从 asyncio.create_task 升级为持久化作业：
- 作业状态持久化到数据库
- 心跳机制检测超时
- 支持取消/重试/恢复
- Worker 独立于 Web 生命周期

状态机：pending → queued → running → validating → writing → activating → completed
                                                                          ↘ failed
                                                                          ↘ canceled
                                                                          ↘ timed_out
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset_models import ImportJob, JobStatus


# 合法状态转换
RUNNING_STATUSES = (
    JobStatus.running,
    JobStatus.validating,
    JobStatus.writing,
    JobStatus.activating,
)

ACTIVE_STATUSES = (
    JobStatus.pending,
    JobStatus.queued,
    *RUNNING_STATUSES,
)

_VALID_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.pending: {JobStatus.queued, JobStatus.canceled},
    JobStatus.queued: {JobStatus.running, JobStatus.canceled, JobStatus.timed_out},
    JobStatus.running: {JobStatus.validating, JobStatus.failed, JobStatus.canceled, JobStatus.timed_out},
    JobStatus.validating: {JobStatus.writing, JobStatus.failed, JobStatus.canceled},
    JobStatus.writing: {JobStatus.activating, JobStatus.failed, JobStatus.canceled},
    JobStatus.activating: {JobStatus.completed, JobStatus.failed, JobStatus.canceled},
    JobStatus.completed: set(),
    JobStatus.failed: {JobStatus.pending},  # 重试时回到 pending
    JobStatus.canceled: set(),
    JobStatus.timed_out: {JobStatus.pending},  # 重试时回到 pending
}


class ImportJobService:
    """导入作业管理服务"""

    @staticmethod
    async def create_job(
        db: AsyncSession,
        project_id: UUID,
        year: int,
        artifact_id: UUID | None = None,
        custom_mapping: dict | None = None,
        options: dict | None = None,
        created_by: UUID | None = None,
    ) -> ImportJob:
        """创建导入作业"""
        job = ImportJob(
            id=uuid.uuid4(),
            project_id=project_id,
            year=year,
            status=JobStatus.pending,
            artifact_id=artifact_id,
            custom_mapping=custom_mapping,
            options=options,
            created_by=created_by,
        )
        db.add(job)
        await db.flush()
        return job

    @staticmethod
    async def set_progress(
        db: AsyncSession,
        job_id: UUID,
        *,
        progress_pct: int,
        progress_message: str | None = None,
        current_phase: str | None = None,
    ) -> None:
        """Persist heartbeat/progress for a running job without changing status."""
        values: dict = {
            "progress_pct": max(0, min(progress_pct, 100)),
            "heartbeat_at": datetime.utcnow(),
        }
        if progress_message is not None:
            values["progress_message"] = progress_message
        if current_phase is not None:
            values["current_phase"] = current_phase
        await db.execute(
            sa.update(ImportJob).where(ImportJob.id == job_id).values(**values)
        )

    @staticmethod
    async def transition(
        db: AsyncSession,
        job_id: UUID,
        new_status: JobStatus,
        progress_pct: int | None = None,
        progress_message: str | None = None,
        error_message: str | None = None,
        result_summary: dict | None = None,
    ) -> ImportJob:
        """状态转换（严格校验合法性）"""
        result = await db.execute(
            sa.select(ImportJob).where(ImportJob.id == job_id)
        )
        job = result.scalar_one_or_none()
        if not job:
            raise ValueError(f"Job {job_id} not found")

        valid_next = _VALID_TRANSITIONS.get(job.status, set())
        if new_status not in valid_next:
            raise ValueError(
                f"Invalid transition: {job.status.value} → {new_status.value}. "
                f"Valid: {[s.value for s in valid_next]}"
            )

        job.status = new_status
        job.current_phase = new_status.value

        if progress_pct is not None:
            job.progress_pct = progress_pct
        if progress_message is not None:
            job.progress_message = progress_message
        if error_message is not None:
            job.error_message = error_message
        if result_summary is not None:
            job.result_summary = result_summary

        # 时间戳
        now = datetime.utcnow()
        if new_status == JobStatus.running and not job.started_at:
            job.started_at = now
        if new_status in (JobStatus.completed, JobStatus.failed, JobStatus.canceled, JobStatus.timed_out):
            job.completed_at = now

        # 心跳
        job.heartbeat_at = now

        return job

    @staticmethod
    async def claim_queued_job(db: AsyncSession, job_id: UUID) -> ImportJob | None:
        """Atomically claim a queued job for execution.

        The project-level queue lock prevents normal duplicate submissions. This
        extra compare-and-set makes recovery/worker races harmless: only one
        runner can move the job from queued to running.
        """
        now = datetime.utcnow()
        result = await db.execute(
            sa.update(ImportJob)
            .where(
                ImportJob.id == job_id,
                ImportJob.status == JobStatus.queued,
            )
            .values(
                status=JobStatus.running,
                current_phase=JobStatus.running.value,
                progress_pct=1,
                progress_message="开始导入",
                started_at=now,
                heartbeat_at=now,
            )
            .returning(ImportJob)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def active_project_job_exists(
        db: AsyncSession,
        project_id: UUID,
        *,
        excluding_job_id: UUID | None = None,
    ) -> bool:
        query = sa.select(sa.func.count()).select_from(ImportJob).where(
            ImportJob.project_id == project_id,
            ImportJob.status.in_(RUNNING_STATUSES),
        )
        if excluding_job_id is not None:
            query = query.where(ImportJob.id != excluding_job_id)
        result = await db.execute(query)
        return int(result.scalar_one() or 0) > 0

    @staticmethod
    async def heartbeat(db: AsyncSession, job_id: UUID) -> None:
        """更新心跳时间（worker 定期调用）"""
        await db.execute(
            sa.update(ImportJob).where(ImportJob.id == job_id).values(
                heartbeat_at=datetime.utcnow()
            )
        )

    @staticmethod
    async def check_timed_out(db: AsyncSession) -> list[ImportJob]:
        """检测超时作业（心跳超过 timeout_seconds 未更新）

        由定时任务调用，将超时作业标记为 timed_out。
        """
        now = datetime.utcnow()
        running_statuses = [JobStatus.queued, JobStatus.running, JobStatus.validating,
                           JobStatus.writing, JobStatus.activating]

        result = await db.execute(
            sa.select(ImportJob).where(
                ImportJob.status.in_(running_statuses),
                ImportJob.heartbeat_at.isnot(None),
            )
        )
        jobs = result.scalars().all()

        timed_out_jobs = []
        for job in jobs:
            elapsed = (now - job.heartbeat_at).total_seconds()
            if elapsed > job.timeout_seconds:
                valid_next = _VALID_TRANSITIONS.get(job.status, set())
                if JobStatus.timed_out in valid_next:
                    job.status = JobStatus.timed_out
                    job.completed_at = now
                    job.error_message = f"作业超时（{elapsed:.0f}s > {job.timeout_seconds}s）"
                    timed_out_jobs.append(job)

        return timed_out_jobs

    @staticmethod
    async def retry(db: AsyncSession, job_id: UUID) -> ImportJob:
        """重试失败/超时的作业"""
        result = await db.execute(
            sa.select(ImportJob).where(ImportJob.id == job_id)
        )
        job = result.scalar_one_or_none()
        if not job:
            raise ValueError(f"Job {job_id} not found")

        if job.status not in (JobStatus.failed, JobStatus.timed_out):
            raise ValueError(f"只能重试 failed/timed_out 状态的作业，当前: {job.status.value}")

        if job.retry_count >= job.max_retries:
            raise ValueError(f"已达最大重试次数 ({job.max_retries})")

        job.status = JobStatus.pending
        job.retry_count += 1
        job.progress_pct = 0
        job.progress_message = f"第 {job.retry_count} 次重试"
        job.error_message = None
        job.started_at = None
        job.completed_at = None
        job.heartbeat_at = None
        job.current_phase = JobStatus.pending.value

        return job

    @staticmethod
    async def cancel(db: AsyncSession, job_id: UUID) -> ImportJob:
        """取消作业"""
        result = await db.execute(
            sa.select(ImportJob).where(ImportJob.id == job_id)
        )
        job = result.scalar_one_or_none()
        if not job:
            raise ValueError(f"Job {job_id} not found")

        valid_next = _VALID_TRANSITIONS.get(job.status, set())
        if JobStatus.canceled not in valid_next:
            raise ValueError(f"当前状态 {job.status.value} 不可取消")

        job.status = JobStatus.canceled
        job.completed_at = datetime.utcnow()
        return job

    @staticmethod
    async def get_job(db: AsyncSession, job_id: UUID) -> ImportJob | None:
        """查询作业"""
        result = await db.execute(
            sa.select(ImportJob).where(ImportJob.id == job_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_jobs(
        db: AsyncSession, project_id: UUID, year: int | None = None
    ) -> list[ImportJob]:
        """查询作业历史"""
        query = sa.select(ImportJob).where(
            ImportJob.project_id == project_id
        )
        if year:
            query = query.where(ImportJob.year == year)
        query = query.order_by(ImportJob.created_at.desc())
        result = await db.execute(query)
        return list(result.scalars().all())
