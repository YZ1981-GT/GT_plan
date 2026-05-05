"""归档编排服务 — ArchiveOrchestrator

Refinement Round 1 — 需求 5：将三个归档端点合并为单一编排流程。

串行执行：
  1. gate_engine.evaluate('export_package') → 不通过则 fail
  2. wp_storage.archive_project(project_id) → 锁底稿
  3. if push_to_cloud: private_storage.push_to_cloud(project_id)
  4. if purge_local: data_lifecycle.archive_project_data(project_id)

失败时记录 failed_section / failed_reason，支持断点续传（从 last_succeeded_section 下一步开始）。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.archive_models import ArchiveJob

logger = logging.getLogger(__name__)

# 硬编码章节顺序（Task 14 会创建 archive_section_registry，本任务先用硬编码）
ARCHIVE_SECTIONS = ["gate", "wp_storage", "push_to_cloud", "purge_local"]


class ArchiveOrchestrator:
    """归档编排器

    同步执行各归档步骤，每步成功更新 last_succeeded_section，
    失败记录 failed_section + failed_reason。
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def orchestrate(
        self,
        project_id: uuid.UUID,
        scope: str = "final",
        push_to_cloud: bool = False,
        purge_local: bool = False,
        gate_eval_id: uuid.UUID | None = None,
        initiated_by: uuid.UUID | None = None,
    ) -> ArchiveJob:
        """创建归档作业并串行执行各步骤。"""
        job = ArchiveJob(
            id=uuid.uuid4(),
            project_id=project_id,
            scope=scope,
            status="running",
            push_to_cloud=push_to_cloud,
            purge_local=purge_local,
            gate_eval_id=gate_eval_id,
            started_at=datetime.now(timezone.utc),
            initiated_by=initiated_by,
        )
        self.db.add(job)
        await self.db.flush()

        # 构建要执行的步骤列表
        steps = self._build_steps(push_to_cloud, purge_local)

        for section_name, step_func in steps:
            try:
                await step_func(project_id, gate_eval_id)
                job.last_succeeded_section = section_name
                await self.db.flush()
            except Exception as exc:
                logger.error(
                    "[ARCHIVE_ORCHESTRATOR] section=%s project=%s error=%s",
                    section_name,
                    project_id,
                    exc,
                )
                job.status = "failed"
                job.failed_section = section_name
                job.failed_reason = str(exc)[:500]
                job.finished_at = datetime.now(timezone.utc)
                await self.db.flush()
                return job

        # 全部成功
        job.status = "succeeded"
        job.finished_at = datetime.now(timezone.utc)
        await self.db.flush()
        return job

    async def retry(
        self,
        job_id: uuid.UUID,
        initiated_by: uuid.UUID | None = None,
    ) -> ArchiveJob:
        """从 last_succeeded_section 的下一步开始重试。"""
        stmt = select(ArchiveJob).where(ArchiveJob.id == job_id)
        result = await self.db.execute(stmt)
        job = result.scalar_one_or_none()
        if not job:
            raise ValueError(f"ArchiveJob {job_id} not found")
        if job.status not in ("failed", "partial"):
            raise ValueError(f"ArchiveJob {job_id} status={job.status}, cannot retry")

        # 重置状态
        job.status = "running"
        job.failed_section = None
        job.failed_reason = None
        job.finished_at = None
        await self.db.flush()

        # 构建步骤并跳过已完成的
        steps = self._build_steps(job.push_to_cloud, job.purge_local)
        start_from = self._get_next_section_index(
            steps, job.last_succeeded_section
        )

        for section_name, step_func in steps[start_from:]:
            try:
                await step_func(job.project_id, job.gate_eval_id)
                job.last_succeeded_section = section_name
                await self.db.flush()
            except Exception as exc:
                logger.error(
                    "[ARCHIVE_ORCHESTRATOR_RETRY] section=%s job=%s error=%s",
                    section_name,
                    job_id,
                    exc,
                )
                job.status = "failed"
                job.failed_section = section_name
                job.failed_reason = str(exc)[:500]
                job.finished_at = datetime.now(timezone.utc)
                await self.db.flush()
                return job

        # 全部成功
        job.status = "succeeded"
        job.finished_at = datetime.now(timezone.utc)
        await self.db.flush()
        return job

    async def get_job(self, job_id: uuid.UUID) -> dict[str, Any] | None:
        """获取归档作业详情。"""
        stmt = select(ArchiveJob).where(ArchiveJob.id == job_id)
        result = await self.db.execute(stmt)
        job = result.scalar_one_or_none()
        if not job:
            return None
        return self._job_to_dict(job)

    # ── 内部步骤实现 ──────────────────────────────────────────

    def _build_steps(
        self, push_to_cloud: bool, purge_local: bool
    ) -> list[tuple[str, Any]]:
        """构建要执行的步骤列表（根据选项动态组合）。"""
        steps: list[tuple[str, Any]] = [
            ("gate", self._step_gate),
            ("wp_storage", self._step_wp_storage),
        ]
        if push_to_cloud:
            steps.append(("push_to_cloud", self._step_push_to_cloud))
        if purge_local:
            steps.append(("purge_local", self._step_purge_local))
        return steps

    def _get_next_section_index(
        self,
        steps: list[tuple[str, Any]],
        last_succeeded: str | None,
    ) -> int:
        """找到 last_succeeded_section 之后的下一个步骤索引。"""
        if last_succeeded is None:
            return 0
        for i, (name, _) in enumerate(steps):
            if name == last_succeeded:
                return i + 1
        return 0

    async def _step_gate(
        self, project_id: uuid.UUID, gate_eval_id: uuid.UUID | None
    ) -> None:
        """步骤 1：门禁检查（export_package）。"""
        from app.services.gate_engine import gate_engine

        # 如果传入了 gate_eval_id，验证其有效性
        if gate_eval_id:
            from app.services.gate_eval_store import validate_gate_eval

            is_valid, reason = await validate_gate_eval(
                str(gate_eval_id),
                project_id=project_id,
                gate_type="export_package",
                require_ready=True,
            )
            if is_valid:
                return  # gate_eval_id 有效且 ready，跳过重新评估
            # gate_eval_id 无效，继续执行完整评估
            logger.warning(
                "[ARCHIVE_ORCHESTRATOR] gate_eval_id invalid: %s, reason=%s, "
                "falling back to full evaluation",
                gate_eval_id,
                reason,
            )

        # 执行 gate 评估
        # 使用一个占位 actor_id（归档由系统发起）
        actor_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
        result = await gate_engine.evaluate(
            db=self.db,
            gate_type="export_package",
            project_id=project_id,
            wp_id=None,
            actor_id=actor_id,
            context={"source": "archive_orchestrator"},
        )
        if result.decision == "block":
            blocking_findings = [
                f.message
                for f in (result.hit_rules or [])
                if f.severity == "blocking"
            ]
            raise RuntimeError(
                f"Gate export_package blocked: {'; '.join(blocking_findings) or 'blocked'}"
            )

    async def _step_wp_storage(
        self, project_id: uuid.UUID, gate_eval_id: uuid.UUID | None
    ) -> None:
        """步骤 2：锁定底稿（wp_storage.archive_project）。"""
        from app.services.wp_storage_service import WpStorageService

        svc = WpStorageService(self.db)
        await svc.archive_project(project_id)

    async def _step_push_to_cloud(
        self, project_id: uuid.UUID, gate_eval_id: uuid.UUID | None
    ) -> None:
        """步骤 3：推送到云端（private_storage）。"""
        from app.services.private_storage_service import ProjectArchiveService

        svc = ProjectArchiveService()
        await svc.archive_project(
            self.db, project_id, push_to_cloud=True, cleanup_local=False
        )

    async def _step_purge_local(
        self, project_id: uuid.UUID, gate_eval_id: uuid.UUID | None
    ) -> None:
        """步骤 4：归档项目数据（软删除）。"""
        from app.services.data_lifecycle_service import DataLifecycleService

        svc = DataLifecycleService(self.db)
        await svc.archive_project_data(project_id)

    # ── 工具方法 ──────────────────────────────────────────────

    @staticmethod
    def _job_to_dict(job: ArchiveJob) -> dict[str, Any]:
        """将 ArchiveJob ORM 对象转为字典。"""
        return {
            "id": str(job.id),
            "project_id": str(job.project_id),
            "scope": job.scope,
            "status": job.status,
            "push_to_cloud": job.push_to_cloud,
            "purge_local": job.purge_local,
            "gate_eval_id": str(job.gate_eval_id) if job.gate_eval_id else None,
            "last_succeeded_section": job.last_succeeded_section,
            "failed_section": job.failed_section,
            "failed_reason": job.failed_reason,
            "section_progress": job.section_progress,
            "output_url": job.output_url,
            "manifest_hash": job.manifest_hash,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "initiated_by": str(job.initiated_by) if job.initiated_by else None,
        }
