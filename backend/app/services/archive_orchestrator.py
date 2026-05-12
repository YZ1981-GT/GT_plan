"""归档编排服务 — ArchiveOrchestrator

Refinement Round 1 — 需求 5：将三个归档端点合并为单一编排流程。

串行执行：
  1. gate_engine.evaluate('export_package') → 不通过则 fail
  2. wp_storage.archive_project(project_id) → 锁底稿
  3. if push_to_cloud: private_storage.push_to_cloud(project_id)
  4. if purge_local: data_lifecycle.archive_project_data(project_id)

失败时记录 failed_section / failed_reason，支持断点续传（从 last_succeeded_section 下一步开始）。

Task 16 增强：归档完成后调用 ExportIntegrityService.persist_checks 记录各章节 SHA-256，
并将整体 manifest_hash 写入 ArchiveJob。persist_hash_checks 失败不阻断归档。
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
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
        """创建归档作业并串行执行各步骤。

        幂等逻辑（R6 Task 16）：同一 project_id 24h 内有
        status in ('succeeded','running') 的 ArchiveJob 则直接返回，不重复打包。
        """
        # ── R6 幂等检查：24h 内已有 succeeded/running 的作业则直接返回 ──
        existing_job = await self._find_recent_job(project_id)
        if existing_job is not None:
            logger.info(
                "[ARCHIVE_ORCHESTRATOR] idempotent hit: project=%s existing_job=%s status=%s",
                project_id,
                existing_job.id,
                existing_job.status,
            )
            return existing_job

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
                # DEPRECATED: UI only, routing uses section_progress (see Batch 2-6)
                job.last_succeeded_section = section_name
                # R1 Bug Fix 5: 断点续传改用 section_progress 记录每步状态
                if job.section_progress is None:
                    job.section_progress = {}
                job.section_progress[section_name] = {
                    "status": "succeeded",
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                }
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

        # 全部成功 — 记录归档完整性哈希
        await self._persist_integrity_hashes(job)

        # 归档成功 — 写入 Project.archived_at + retention_until（需求 11）
        await self._set_project_retention(project_id)

        job.status = "succeeded"
        job.finished_at = datetime.now(timezone.utc)
        await self.db.flush()

        # 归档成功 — 通知项目成员
        await self._notify_project_members(project_id, job)

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

        # 构建步骤并跳过已完成的（R1 Bug Fix 5 + Batch 2-6：section_progress 为权威来源）
        steps = self._build_steps(job.push_to_cloud, job.purge_local)
        start_from = self._get_next_section_index(steps, job.section_progress)

        for section_name, step_func in steps[start_from:]:
            try:
                await step_func(job.project_id, job.gate_eval_id)
                # DEPRECATED: UI only, routing uses section_progress (see Batch 2-6)
                job.last_succeeded_section = section_name
                # R1 Bug Fix 5: 断点续传改用 section_progress 记录每步状态
                if job.section_progress is None:
                    job.section_progress = {}
                job.section_progress[section_name] = {
                    "status": "succeeded",
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                }
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

        # 全部成功 — 记录归档完整性哈希
        await self._persist_integrity_hashes(job)

        # 归档成功 — 写入 Project.archived_at + retention_until（需求 11）
        await self._set_project_retention(job.project_id)

        job.status = "succeeded"
        job.finished_at = datetime.now(timezone.utc)
        await self.db.flush()

        # 归档成功 — 通知项目成员
        await self._notify_project_members(job.project_id, job)

        return job

    async def get_job(self, job_id: uuid.UUID) -> dict[str, Any] | None:
        """获取归档作业详情。"""
        stmt = select(ArchiveJob).where(ArchiveJob.id == job_id)
        result = await self.db.execute(stmt)
        job = result.scalar_one_or_none()
        if not job:
            return None
        return self._job_to_dict(job)

    # ── 归档保留期设置（需求 11）──────────────────────────────────

    async def _set_project_retention(self, project_id: uuid.UUID) -> None:
        """归档成功后写入 Project.archived_at + retention_until。

        retention_until = archived_at + 10 years (3652 days)。
        失败不阻断归档流程。
        """
        try:
            from datetime import timedelta

            from app.models.core import Project

            stmt = select(Project).where(Project.id == project_id)
            result = await self.db.execute(stmt)
            project = result.scalar_one_or_none()
            if project is None:
                logger.warning(
                    "[ARCHIVE_ORCHESTRATOR] _set_project_retention: project not found: %s",
                    project_id,
                )
                return

            now = datetime.now(timezone.utc)
            project.archived_at = now
            # 10 years ≈ 3652 days (accounts for ~2.5 leap years in a decade)
            project.retention_until = now + timedelta(days=3652)
            await self.db.flush()

            logger.info(
                "[ARCHIVE_ORCHESTRATOR] retention set: project=%s archived_at=%s retention_until=%s",
                project_id,
                project.archived_at.isoformat(),
                project.retention_until.isoformat(),
            )
        except Exception as exc:
            # 保留期设置失败不阻断归档
            logger.warning(
                "[ARCHIVE_ORCHESTRATOR] _set_project_retention failed "
                "(non-blocking): project=%s error=%s",
                project_id,
                exc,
            )

    # ── 归档完成通知 ──────────────────────────────────────────────

    async def _notify_project_members(
        self, project_id: uuid.UUID, job: ArchiveJob
    ) -> None:
        """归档成功后通知项目所有成员。

        失败不阻断归档流程（try/except + warning）。
        """
        try:
            from app.models.core import Project, ProjectUser
            from app.services.notification_service import NotificationService
            from app.services.notification_types import (
                ARCHIVE_DONE,
                NOTIFICATION_META,
            )

            # 查询项目名称
            project_stmt = select(Project).where(Project.id == project_id)
            project_result = await self.db.execute(project_stmt)
            project = project_result.scalar_one_or_none()
            project_name = project.name if project else str(project_id)

            # 查询项目成员
            members_stmt = select(ProjectUser.user_id).where(
                ProjectUser.project_id == project_id,
                ProjectUser.is_deleted == False,  # noqa: E712
            )
            members_result = await self.db.execute(members_stmt)
            user_ids = [row[0] for row in members_result.all()]

            if not user_ids:
                logger.info(
                    "[ARCHIVE_ORCHESTRATOR] no project members to notify: project=%s",
                    project_id,
                )
                return

            # 构建通知内容
            meta = NOTIFICATION_META[ARCHIVE_DONE]
            title = meta["title_template"]
            content = meta["content_template"].format(
                project_name=project_name,
                job_id=str(job.id),
            )
            metadata = {
                "project_id": str(project_id),
                "job_id": str(job.id),
                "object_type": "archive_job",
                "object_id": str(job.id),
            }

            # 发送通知
            notif_svc = NotificationService(self.db)
            sent_count = await notif_svc.send_notification_to_many(
                user_ids=user_ids,
                notification_type=ARCHIVE_DONE,
                title=title,
                content=content,
                metadata=metadata,
            )

            logger.info(
                "[ARCHIVE_ORCHESTRATOR] archive_done notifications sent: "
                "project=%s job=%s recipients=%d sent=%d",
                project_id,
                job.id,
                len(user_ids),
                sent_count,
            )

        except Exception as exc:
            # 通知失败不阻断归档
            logger.warning(
                "[ARCHIVE_ORCHESTRATOR] _notify_project_members failed "
                "(non-blocking): project=%s error=%s",
                project_id,
                exc,
            )

    # ── 归档完整性哈希 ──────────────────────────────────────────

    async def _persist_integrity_hashes(self, job: ArchiveJob) -> None:
        """归档成功后计算各章节 SHA-256 并持久化到 evidence_hash_checks。

        失败不阻断归档（try/except + warning），符合需求 5/6 语义：
        "persist_hash_checks 失败不阻断归档"。
        """
        try:
            from app.services import archive_section_registry
            from app.services.export_integrity_service import export_integrity_service

            # 生成各章节内容
            sections = await archive_section_registry.generate_all(
                job.project_id, self.db
            )

            section_hashes: list[dict] = []
            hash_values: list[str] = []

            for filename, content in sections:
                if content is None:
                    continue

                # 计算 SHA-256
                if isinstance(content, (bytes, bytearray)):
                    sha = hashlib.sha256(content).hexdigest()
                elif isinstance(content, Path):
                    # 文件路径：分块读取
                    h = hashlib.sha256()
                    if content.exists():
                        with open(content, "rb") as f:
                            while True:
                                chunk = f.read(65536)
                                if not chunk:
                                    break
                                h.update(chunk)
                    sha = h.hexdigest()
                else:
                    # 其他类型尝试转 bytes
                    sha = hashlib.sha256(
                        str(content).encode("utf-8")
                    ).hexdigest()

                section_hashes.append({
                    "file_path": filename,
                    "sha256": sha,
                })
                hash_values.append(sha)

            # 持久化到 evidence_hash_checks
            if section_hashes:
                await export_integrity_service.persist_checks(
                    db=self.db,
                    export_id=str(job.id),
                    file_checks=section_hashes,
                )

            # 计算整体 manifest_hash（所有章节 hash 拼接后再 SHA-256）
            if hash_values:
                combined = "".join(hash_values)
                job.manifest_hash = hashlib.sha256(
                    combined.encode("utf-8")
                ).hexdigest()
                await self.db.flush()

            logger.info(
                "[ARCHIVE_ORCHESTRATOR] integrity hashes persisted: "
                "job=%s sections=%d manifest_hash=%s",
                job.id,
                len(section_hashes),
                job.manifest_hash,
            )

        except Exception as exc:
            # persist_hash_checks 失败不阻断归档
            logger.warning(
                "[ARCHIVE_ORCHESTRATOR] persist_integrity_hashes failed "
                "(non-blocking): job=%s error=%s",
                job.id,
                exc,
            )

    # ── 幂等查询（R6 Task 16）──────────────────────────────────

    async def _find_recent_job(self, project_id: uuid.UUID) -> ArchiveJob | None:
        """查找同一 project_id 24h 内 status in ('succeeded','running') 的作业。

        返回最近一条匹配的 ArchiveJob，若无则返回 None。
        """
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        stmt = (
            select(ArchiveJob)
            .where(
                ArchiveJob.project_id == project_id,
                ArchiveJob.status.in_(["succeeded", "running"]),
                ArchiveJob.created_at >= cutoff,
            )
            .order_by(ArchiveJob.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

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
        section_progress: dict | None,
    ) -> int:
        """找到 section_progress 中第一个未 succeeded 的步骤索引。

        Batch 2-6: section_progress 为权威路由来源；last_succeeded_section
        字段仍保留写入（向后兼容 + 日志用），但不参与路由判断。

        Args:
            steps: 待执行步骤列表
            section_progress: 每步执行状态的 dict，形如
                {"gate": {"status": "succeeded", "finished_at": "..."}}

        Returns:
            下一个待执行步骤的索引；section_progress 为 None/空时返回 0（从头开始）。
        """
        if not section_progress:
            return 0

        # 找到第一个未 succeeded 的步骤
        for i, (name, _) in enumerate(steps):
            sp = section_progress.get(name)
            if not sp or sp.get("status") != "succeeded":
                return i
        # 全部已完成
        return len(steps)

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
        """将 ArchiveJob ORM 对象转为字典。

        Batch 3-4 说明：`section_progress` is the authoritative routing source;
        `last_succeeded_section` is kept for UI compatibility only (see Batch 2-6).
        前端 UI 应优先读 section_progress 计算进度百分比，last_succeeded_section
        仅作为失败时"最后成功章节"的文案展示。
        """
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
