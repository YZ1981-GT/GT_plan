"""归档编排服务 — ArchiveOrchestrator

Refinement Round 1 — 需求 5：将三个归档端点合并为单一编排流程。

spec attachment-archive-and-a-class-evidence（ADR-AE-02~05）改造后串行执行：
  1. gate          门禁：与归档向导同口径现算（就绪检查 + 完整性自检），有阻断项即失败（``archive_gate``）
  2. package       按数据库清单打归档包（``archive_package_builder``），缺件即失败；写 manifest_hash、
                   output_url 与完整性记录（包文件路径 + sha256）
  3. push_to_cloud （可选）上传归档包本身，失败抛错
  4. lock          项目状态改「已归档」+ 归档时间 / 保留期，项目内未删除底稿改「已归档」
  5. purge_local   （可选）项目数据软删除

任一步失败 ⇒ 任务失败并记录失败步骤与原因（完整问题清单在 ``section_progress[步骤].problems``）；只有
成员通知失败不影响结果。断点续传：从 ``section_progress`` 第一个未成功的步骤继续。

改造前：打包只把 ``storage/projects/{pid}`` 打 tar，失败返回 ``{"error"}`` 不抛、编排不看返回值；章节只算
哈希不进包；保留期写入与哈希持久化失败都不阻断；不改项目状态 ⇒ 归档成功后项目仍可编辑；
``section_progress`` 原地改 JSONB 从未落库。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.archive_models import ArchiveJob

logger = logging.getLogger(__name__)

ARCHIVE_SECTIONS = ["gate", "package", "push_to_cloud", "lock", "purge_local"]

#: 保留期：归档后 10 年（≈3652 天，含闰年）
RETENTION_DAYS = 3652
_REASON_LIMIT = 2000


def package_download_url(project_id: uuid.UUID, job_id: uuid.UUID) -> str:
    return f"/api/projects/{project_id}/archive/jobs/{job_id}/package"


class ArchiveOrchestrator:
    """归档编排器：每步成功写进度，失败记录 failed_section + failed_reason。"""

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

        幂等（R6 Task 16）：同一项目 24h 内有 succeeded / running 的作业则直接返回，不重复打包。
        """
        existing_job = await self._find_recent_job(project_id)
        if existing_job is not None:
            logger.info("[ARCHIVE_ORCHESTRATOR] idempotent hit: project=%s job=%s status=%s",
                        project_id, existing_job.id, existing_job.status)
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
        return await self._run(job, start_from=0)

    async def retry(self, job_id: uuid.UUID, initiated_by: uuid.UUID | None = None) -> ArchiveJob:
        """从第一个未成功的步骤继续。"""
        job = (await self.db.execute(select(ArchiveJob).where(ArchiveJob.id == job_id))).scalar_one_or_none()
        if not job:
            raise ValueError(f"ArchiveJob {job_id} not found")
        if job.status not in ("failed", "partial"):
            raise ValueError(f"ArchiveJob {job_id} status={job.status}, cannot retry")
        job.status = "running"
        job.failed_section = None
        job.failed_reason = None
        job.finished_at = None
        await self.db.flush()
        steps = self._build_steps(job.push_to_cloud, job.purge_local)
        return await self._run(job, start_from=self._get_next_section_index(steps, job.section_progress))

    async def get_job(self, job_id: uuid.UUID) -> dict[str, Any] | None:
        job = (await self.db.execute(select(ArchiveJob).where(ArchiveJob.id == job_id))).scalar_one_or_none()
        return self._job_to_dict(job) if job else None

    # ── 执行 ──────────────────────────────────────────────────

    def _set_progress(self, job: ArchiveJob, name: str, value: dict[str, Any]) -> None:
        # 换新字典：原地改 JSONB 不会被标脏，改造前的进度从未落库
        job.section_progress = {**(job.section_progress or {}), name: value}

    async def _run(self, job: ArchiveJob, *, start_from: int) -> ArchiveJob:
        steps = self._build_steps(job.push_to_cloud, job.purge_local)
        for section_name, step_func in steps[start_from:]:
            try:
                extra = await step_func(job) or {}
            except Exception as exc:  # noqa: BLE001 — 任一步失败即任务失败（ADR-AE-02）
                problems = list(getattr(exc, "problems", []) or [])
                logger.error("[ARCHIVE_ORCHESTRATOR] section=%s job=%s project=%s error=%s",
                             section_name, job.id, job.project_id, exc)
                job.status = "failed"
                job.failed_section = section_name
                job.failed_reason = str(exc)[:_REASON_LIMIT]
                job.finished_at = datetime.now(timezone.utc)
                self._set_progress(job, section_name, {
                    "status": "failed", "finished_at": job.finished_at.isoformat(), "problems": problems[:500],
                })
                await self.db.flush()
                return job
            job.last_succeeded_section = section_name  # 仅供界面展示；续跑以 section_progress 为准
            self._set_progress(job, section_name, {
                "status": "succeeded", "finished_at": datetime.now(timezone.utc).isoformat(), **extra,
            })
            await self.db.flush()

        job.status = "succeeded"
        job.finished_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self._notify_project_members(job.project_id, job)
        return job

    def _build_steps(self, push_to_cloud: bool, purge_local: bool) -> list[tuple[str, Any]]:
        steps: list[tuple[str, Any]] = [("gate", self._step_gate), ("package", self._step_package)]
        if push_to_cloud:
            steps.append(("push_to_cloud", self._step_push_to_cloud))
        steps.append(("lock", self._step_lock))
        if purge_local:
            steps.append(("purge_local", self._step_purge_local))
        return steps

    def _get_next_section_index(self, steps: list[tuple[str, Any]], section_progress: dict | None) -> int:
        """``section_progress`` 里第一个未 succeeded 的步骤索引；为空时从头开始。"""
        if not section_progress:
            return 0
        for i, (name, _) in enumerate(steps):
            sp = section_progress.get(name)
            if not sp or sp.get("status") != "succeeded":
                return i
        return len(steps)

    # ── 步骤 ──────────────────────────────────────────────────

    async def _step_gate(self, job: ArchiveJob) -> None:
        """门禁：与归档向导同口径现算（就绪检查 + 完整性自检，ADR-AE-14）；客户端带来的评估 id 只作记录。"""
        from app.services import archive_gate

        problems = await archive_gate.archive_gate_problems(self.db, job.project_id, job.initiated_by)
        if problems:
            raise archive_gate.ArchiveGateBlocked(problems)
        return None

    async def _step_package(self, job: ArchiveJob) -> dict[str, Any]:
        """按数据库清单打归档包；缺件抛 ArchivePackageError（带 problems）。"""
        from app.services.archive_package_builder import build_archive_package
        from app.services.export_integrity_service import export_integrity_service

        result = await build_archive_package(self.db, job.project_id, job.id)
        job.manifest_hash = result.manifest_hash
        job.output_url = package_download_url(job.project_id, job.id)
        await export_integrity_service.persist_checks(
            db=self.db, export_id=str(job.id),
            file_checks=[{"file_path": str(result.path.resolve()), "sha256": result.sha256}],
        )
        return {"path": str(result.path.resolve()), "sha256": result.sha256, "size": result.size,
                "manifest_hash": result.manifest_hash, "counts": result.counts, "skipped": result.skipped}

    def _package_from_progress(self, job: ArchiveJob):
        from pathlib import Path

        from app.services.archive_package_builder import file_sha256

        info = (job.section_progress or {}).get("package") or {}
        raw, expected = info.get("path"), info.get("sha256")
        path = Path(raw) if raw else None
        if path is None or not path.is_file() or not expected or file_sha256(path) != expected:
            raise RuntimeError("归档包文件不存在或已被改动，请重新归档")
        return path

    async def _step_push_to_cloud(self, job: ArchiveJob) -> dict[str, Any]:
        """上传归档包本身到云端；失败抛错（ADR-AE-05）。"""
        from app.models.core import Project
        from app.services.cloud_storage_service import CloudStorageService

        path = self._package_from_progress(job)
        project = (await self.db.execute(select(Project).where(Project.id == job.project_id))).scalar_one_or_none()
        result = await CloudStorageService().upload_archive_package(
            job.project_id, (project.client_name or project.name) if project else "unknown",
            _audit_year(project), path,
        )
        return {"remote_key": result.get("remote_key"), "method": result.get("method")}

    async def _step_lock(self, job: ArchiveJob) -> dict[str, Any]:
        """项目状态「已归档」+ 归档时间 / 保留期 + 底稿「已归档」（ADR-AE-04）。

        锁定前的底稿状态记进本步进度（``previous_wp_statuses``），解除归档按它恢复（ADR-AE-13）。
        """
        from app.models.core import Project, ProjectStatus
        from app.models.workpaper_models import WorkingPaper, WpFileStatus

        project = (await self.db.execute(select(Project).where(Project.id == job.project_id))).scalar_one_or_none()
        if project is None:
            raise RuntimeError("项目不存在，无法锁定")
        live = (WorkingPaper.project_id == job.project_id, WorkingPaper.is_deleted == sa.false())
        previous = {
            str(wp_id): getattr(status, "value", status)
            for wp_id, status in (await self.db.execute(
                sa.select(WorkingPaper.id, WorkingPaper.status).where(*live, WorkingPaper.status != WpFileStatus.archived)
            )).all()
        }
        # 归档即锁定 ACNR 地址目录版本（T18 / 需求 7.2）：归档后的底稿地址要按归档当时的目录
        # 版本解析，锁不上就不许归档 —— 否则目录升级后归档项目的地址对不回去，而那时已无法补救。
        # 快照缺失 / 内容不自洽 / 已锁到别的版本 → RegistryLockError 上抛，本步失败、整个归档
        # job 失败、事务不提交（项目状态不会停在半归档）。
        from app.services.acnr.project_registry_lock import lock_project_registry

        await lock_project_registry(self.db, job.project_id)

        now = datetime.now(timezone.utc)
        project.status = ProjectStatus.archived
        project.archived_at = now
        project.retention_until = now + timedelta(days=RETENTION_DAYS)
        res = await self.db.execute(
            sa.update(WorkingPaper).where(*live).values(status=WpFileStatus.archived)
            .execution_options(synchronize_session=False)
        )
        await self.db.flush()
        return {"workpapers_locked": int(res.rowcount or 0), "retention_until": project.retention_until.isoformat(),
                "previous_wp_statuses": previous}

    async def _step_purge_local(self, job: ArchiveJob) -> None:
        """项目数据软删除（可选）。"""
        from app.services.data_lifecycle_service import DataLifecycleService

        await DataLifecycleService(self.db).archive_project_data(job.project_id)
        return None

    # ── 归档完成通知（失败不影响结果）──────────────────────────

    async def _notify_project_members(self, project_id: uuid.UUID, job: ArchiveJob) -> None:
        try:
            from app.models.core import Project, ProjectUser
            from app.services.notification_service import NotificationService
            from app.services.notification_types import ARCHIVE_DONE, NOTIFICATION_META

            project = (await self.db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
            project_name = project.name if project else str(project_id)
            user_ids = [row[0] for row in (await self.db.execute(
                select(ProjectUser.user_id).where(
                    ProjectUser.project_id == project_id, ProjectUser.is_deleted == False,  # noqa: E712
                )
            )).all()]
            if not user_ids:
                logger.info("[ARCHIVE_ORCHESTRATOR] no project members to notify: project=%s", project_id)
                return
            meta = NOTIFICATION_META[ARCHIVE_DONE]
            sent = await NotificationService(self.db).send_notification_to_many(
                user_ids=user_ids,
                notification_type=ARCHIVE_DONE,
                title=meta["title_template"],
                content=meta["content_template"].format(project_name=project_name, job_id=str(job.id)),
                metadata={"project_id": str(project_id), "job_id": str(job.id),
                          "object_type": "archive_job", "object_id": str(job.id)},
            )
            logger.info("[ARCHIVE_ORCHESTRATOR] archive_done notifications sent: project=%s job=%s sent=%d",
                        project_id, job.id, sent)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[ARCHIVE_ORCHESTRATOR] _notify_project_members failed (non-blocking): "
                           "project=%s error=%s", project_id, exc)

    # ── 幂等查询（R6 Task 16）──────────────────────────────────

    async def _find_recent_job(self, project_id: uuid.UUID) -> ArchiveJob | None:
        """24 小时内在跑的作业，或项目仍处于已归档时的成功作业。

        解除归档后成功作业的锁定已撤销：再归档要重新跑（改造前照样命中旧作业 ⇒ 回执「成功」但项目仍可编辑）。
        """
        from app.models.core import Project, ProjectStatus

        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        stmt = (
            select(ArchiveJob)
            .join(Project, Project.id == ArchiveJob.project_id)
            .where(
                ArchiveJob.project_id == project_id,
                ArchiveJob.created_at >= cutoff,
                sa.or_(ArchiveJob.status == "running",
                       sa.and_(ArchiveJob.status == "succeeded", Project.status == ProjectStatus.archived)),
            )
            .order_by(ArchiveJob.created_at.desc())
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    @staticmethod
    def _job_to_dict(job: ArchiveJob) -> dict[str, Any]:
        """``section_progress`` 是续跑与进度的权威来源；``last_succeeded_section`` 仅供界面展示。"""
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
            "section_progress": _public_progress(job.section_progress),
            "output_url": job.output_url,
            "manifest_hash": job.manifest_hash,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "initiated_by": str(job.initiated_by) if job.initiated_by else None,
        }


def _audit_year(project) -> int:
    """云端目录用的审计年度（平台统一口径 ``resolve_project_audit_year``）；解析不出如实报错，不用今年兜底。"""
    from app.services.project_audit_year import resolve_project_audit_year

    year = resolve_project_audit_year(project) if project is not None else None
    if not year:
        raise RuntimeError("项目未设置审计年度（审计期末 / 向导基本信息都没有），无法确定云端归档目录")
    return year


def _public_progress(progress: dict | None) -> dict | None:
    """给界面的进度：锁定步骤的底稿原状态清单只留条数（大项目上千条，轮询不必每次带）。"""
    lock = (progress or {}).get("lock")
    if not isinstance(lock, dict) or "previous_wp_statuses" not in lock:
        return progress
    public_lock = {k: v for k, v in lock.items() if k != "previous_wp_statuses"}
    public_lock["previous_wp_status_count"] = len(lock.get("previous_wp_statuses") or {})
    return {**progress, "lock": public_lock}


async def restore_after_unarchive(db: AsyncSession, project_id: uuid.UUID) -> dict[str, Any]:
    """解除归档 = 锁定的逆操作（ADR-AE-13）：清归档时间 / 保留期，底稿按最近一次锁定记录恢复原状态。

    只认最近一次成功作业的锁定记录、且未恢复过（恢复后记 ``restored_at``，同一记录不会用两次）；只恢复
    当前仍是「已归档」的底稿。没有这样的记录（交付件归档、改造前的旧作业 —— 当时不锁底稿）⇒ 只清时间。
    改造前解除归档只改项目状态：底稿停在「已归档」恒只读，归档时间仍在 ⇒ 独立性门禁跳过、准则切换被拒。
    """
    from app.models.core import Project
    from app.models.workpaper_models import WorkingPaper, WpFileStatus

    project = await db.get(Project, project_id)
    if project is not None:
        project.archived_at = None
        project.retention_until = None
    # 按应用写入的完成时间取最近一次（库默认的创建时间在 PG 是事务开始时间、SQLite 只到秒，同秒两条分不出先后）
    job = (await db.execute(
        select(ArchiveJob)
        .where(ArchiveJob.project_id == project_id, ArchiveJob.status == "succeeded")
        .order_by(ArchiveJob.finished_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    lock = ((job.section_progress or {}).get("lock") if job is not None else None) or {}
    previous = lock.get("previous_wp_statuses")
    if not isinstance(previous, dict) or lock.get("restored_at"):
        await db.flush()
        return {"workpapers_restored": 0, "job_id": None}

    known = {s.value for s in WpFileStatus} - {WpFileStatus.archived.value}
    by_status: dict[str, list[uuid.UUID]] = {}
    for wp_id, status in previous.items():
        if status in known:
            by_status.setdefault(status, []).append(uuid.UUID(wp_id))
    restored = 0
    for status, ids in by_status.items():
        res = await db.execute(
            sa.update(WorkingPaper)
            .where(WorkingPaper.id.in_(ids), WorkingPaper.status == WpFileStatus.archived)
            .values(status=WpFileStatus(status))
            .execution_options(synchronize_session=False)
        )
        restored += int(res.rowcount or 0)
    job.section_progress = {**job.section_progress, "lock": {
        **lock, "restored_at": datetime.now(timezone.utc).isoformat(), "workpapers_restored": restored,
    }}
    await db.flush()
    return {"workpapers_restored": restored, "job_id": str(job.id)}
