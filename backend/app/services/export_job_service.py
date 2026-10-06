"""导出后台任务编排 — Phase 13 Stage 2.5

管理长时间运行的导出任务（全套导出、批量渲染、失败重试）。
统一走 job_id，支持页面刷新恢复与失败项重试。

Phase4 Task 7 扩展：
- recover_stale_running: 中断/超时后的 running 恢复策略（fail-closed）
- get_job_with_items: job + items + 最新 attempt 信息
- get_item_attempts: 某 item 的全部 attempt 历史（按 attempt_no 排序）
- get_job_history: 项目/年度维度的全部 job 历史

Phase4 Task 8 扩展：
- retry_failed_trio: 真正重试失败步骤（调用 executor 步骤入口，
  重新渲染/落盘/指纹/版本），成功项复用前校验文件指纹。
  旧 retry_failed 仅重置状态，retry_failed_trio 是正式替代。
"""

from __future__ import annotations

import logging
import traceback
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase13_models import (
    ExportJob,
    ExportJobAttempt,
    ExportJobAttemptStatus,
    ExportJobItem,
    ExportJobItemStatus,
    ExportJobStatus,
)

if TYPE_CHECKING:
    from app.services.full_deliverables_executor import TrioStepRunner

logger = logging.getLogger(__name__)


class SnapshotConflictError(Exception):
    """快照摘要冲突：当前 readiness 快照与 job 绑定的快照不一致。

    触发场景：重试时发现底层数据已变化，job 绑定的 snapshot 过期。
    调用方应返回 HTTP 409 并建议用户创建新 job（design §七）。
    """

    def __init__(self, message: str, *, job_digest: str, current_digest: str):
        super().__init__(message)
        self.job_digest = job_digest
        self.current_digest = current_digest


class ExportJobService:
    """后台导出任务编排服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_job(
        self,
        project_id: UUID,
        job_type: str,
        payload: dict | None,
        user_id: UUID,
        total: int = 0,
    ) -> ExportJob:
        """创建后台导出任务

        Args:
            project_id: 项目ID
            job_type: 任务类型 (generate/full_package/retry)
            payload: 任务参数 (JSONB)
            user_id: 发起人ID
            total: 预计总项数
        """
        job = ExportJob(
            project_id=project_id,
            job_type=job_type,
            status=ExportJobStatus.queued.value,
            payload=payload or {},
            progress_total=total,
            progress_done=0,
            failed_count=0,
            initiated_by=user_id,
        )
        self.db.add(job)
        await self.db.flush()

        logger.info(
            "创建导出任务: job_id=%s, type=%s, project=%s",
            job.id, job_type, project_id,
        )
        return job

    async def get_job(self, job_id: UUID) -> ExportJob | None:
        """获取任务详情（含明细项）"""
        result = await self.db.execute(
            sa.select(ExportJob).where(ExportJob.id == job_id)
        )
        return result.scalar_one_or_none()

    async def get_job_items(self, job_id: UUID) -> list[ExportJobItem]:
        """获取任务明细项列表"""
        result = await self.db.execute(
            sa.select(ExportJobItem)
            .where(ExportJobItem.job_id == job_id)
            .order_by(ExportJobItem.finished_at.asc().nullsfirst())
        )
        return list(result.scalars().all())

    async def add_item(
        self,
        job_id: UUID,
        word_export_task_id: UUID | None = None,
    ) -> ExportJobItem:
        """添加任务明细项"""
        item = ExportJobItem(
            job_id=job_id,
            word_export_task_id=word_export_task_id,
            status=ExportJobStatus.queued.value,
        )
        self.db.add(item)
        await self.db.flush()
        return item

    async def update_item_status(
        self,
        item_id: UUID,
        status: str,
        error_message: str | None = None,
    ) -> ExportJobItem | None:
        """更新明细项状态"""
        result = await self.db.execute(
            sa.select(ExportJobItem).where(ExportJobItem.id == item_id)
        )
        item = result.scalar_one_or_none()
        if item is None:
            return None

        item.status = status
        if error_message:
            item.error_message = error_message
        if status in (
            ExportJobStatus.succeeded.value,
            ExportJobStatus.failed.value,
        ):
            item.finished_at = datetime.now(timezone.utc)
        await self.db.flush()
        return item

    async def update_progress(
        self,
        job_id: UUID,
        done: int,
        failed: int = 0,
    ) -> ExportJob | None:
        """更新任务进度

        Args:
            job_id: 任务ID
            done: 已完成数
            failed: 失败数
        """
        result = await self.db.execute(
            sa.select(ExportJob).where(ExportJob.id == job_id)
        )
        job = result.scalar_one_or_none()
        if job is None:
            return None

        job.progress_done = done
        job.failed_count = failed

        # Auto-determine job status
        if done + failed >= job.progress_total and job.progress_total > 0:
            if failed == 0:
                job.status = ExportJobStatus.succeeded.value
            elif done > 0:
                job.status = ExportJobStatus.partial_failed.value
            else:
                job.status = ExportJobStatus.failed.value

            # ── Phase 16: 导出完成后自动生成取证包 hash ──
            if job.status == ExportJobStatus.succeeded.value:
                try:
                    from app.services.export_integrity_service import export_integrity_service
                    from pathlib import Path
                    import glob
                    # 查找导出文件
                    export_dir = Path("storage") / "exports" / str(job_id)
                    if export_dir.exists():
                        files = [str(f) for f in export_dir.rglob("*") if f.is_file()]
                        if files:
                            manifest = await export_integrity_service.build_manifest(str(job_id), files)
                            await export_integrity_service.persist_checks(self.db, str(job_id), manifest["files"])
                            logger.info(f"[INTEGRITY] export hash generated: job={job_id} files={len(files)}")
                except Exception as _int_err:
                    logger.warning(f"[INTEGRITY] export hash generation failed: {_int_err}")

        elif done > 0 or failed > 0:
            job.status = ExportJobStatus.running.value

        await self.db.flush()
        logger.info(
            "导出任务进度: job_id=%s, done=%d/%d, failed=%d",
            job_id, done, job.progress_total, failed,
        )
        return job

    async def retry_failed(self, job_id: UUID) -> int:
        """重试失败项

        Only retries items with status='failed'. Returns count of retried items.
        """
        result = await self.db.execute(
            sa.select(ExportJobItem).where(
                ExportJobItem.job_id == job_id,
                ExportJobItem.status == ExportJobStatus.failed.value,
            )
        )
        failed_items = result.scalars().all()

        retried = 0
        for item in failed_items:
            item.status = ExportJobStatus.queued.value
            item.error_message = None
            item.finished_at = None
            retried += 1

        if retried > 0:
            # Reset job status to running
            job_result = await self.db.execute(
                sa.select(ExportJob).where(ExportJob.id == job_id)
            )
            job = job_result.scalar_one_or_none()
            if job:
                job.status = ExportJobStatus.running.value
                job.failed_count = 0
                job.progress_done = max(0, job.progress_done - retried)
            await self.db.flush()

        logger.info("重试失败项: job_id=%s, retried=%d", job_id, retried)
        return retried

    # ------------------------------------------------------------------
    # Phase4 Task 8 — 真正重试失败步骤
    # ------------------------------------------------------------------

    async def retry_failed_trio(
        self,
        job_id: UUID,
        *,
        step_runner: "TrioStepRunner",
        current_snapshot_digest: str | None = None,
    ) -> dict:
        """重试失败的三件套步骤 — 真正调用 executor 步骤入口。

        design §七 / 需求 5.2–5.5：
        1. 锁定 job，确认属于请求 project 且 kind=deliverable_trio
        2. 校验快照一致性：current_snapshot_digest 与 job 绑定的 snapshot
           不一致时抛 SnapshotConflictError（调用方返回 409）
        3. 找出 status=failed 的正式 trio item
        4. 对已成功项验证文件指纹，不重试
        5. 每个失败项：创建新 attempt → 在 begin_nested 内调用
           step_runner.run_step → 成功则更新 item+attempt / 失败则
           只新增失败 attempt 并保留旧失败记录
        6. 重新聚合 job 状态和 trio_succeeded
        7. 服务仅 flush，由 router commit

        Args:
            job_id: 要重试的 job ID
            step_runner: 步骤执行回调（TrioStepRunner 协议）
            current_snapshot_digest: 当前 readiness 快照摘要，
                用于一致性校验。None 则跳过摘要比较。

        Returns:
            dict 包含 retried/succeeded/failed 计数和 outcomes

        Raises:
            ValueError: job 不存在或不是 deliverable_trio
            SnapshotConflictError: 快照不一致
        """
        from app.models.phase13_models import DeliverableSnapshot
        from app.services.full_deliverables_executor import (
            AUDIT_REPORT_DEPENDENCIES,
            TRIO_STEP_KEYS,
            aggregate_trio_status,
        )

        # 1. 加载 job
        job = await self.get_job(job_id)
        if job is None:
            raise ValueError(f"job 不存在: {job_id}")
        if job.kind != "deliverable_trio":
            raise ValueError(
                f"job 不是 deliverable_trio 类型: kind={job.kind}"
            )

        # 2. 快照一致性校验
        if current_snapshot_digest is not None and job.snapshot_id is not None:
            snap_result = await self.db.execute(
                sa.select(DeliverableSnapshot).where(
                    DeliverableSnapshot.id == job.snapshot_id,
                )
            )
            snap = snap_result.scalar_one_or_none()
            if snap is not None and snap.digest != current_snapshot_digest:
                raise SnapshotConflictError(
                    "源数据已变化，job 绑定的快照与当前 readiness 不一致，"
                    "请创建新的三件套 job",
                    job_digest=snap.digest,
                    current_digest=current_snapshot_digest,
                )

        # 3. 获取正式 trio items（按 sequence 排序）
        items_result = await self.db.execute(
            sa.select(ExportJobItem)
            .where(
                ExportJobItem.job_id == job_id,
                ExportJobItem.step_key.in_(TRIO_STEP_KEYS),
            )
            .order_by(ExportJobItem.sequence.asc())
        )
        all_items = list(items_result.scalars().all())

        # 4. 分离失败项和已成功项
        failed_items = [
            i for i in all_items
            if i.status in (
                ExportJobItemStatus.failed.value,
                ExportJobItemStatus.blocked.value,
            )
        ]
        succeeded_items = [
            i for i in all_items
            if i.status == ExportJobItemStatus.succeeded.value
        ]

        if not failed_items:
            logger.info("retry_failed_trio: 无失败项 job=%s", job_id)
            return {
                "retried": 0,
                "succeeded": 0,
                "failed": 0,
                "skipped_succeeded": len(succeeded_items),
                "outcomes": [],
            }

        # 5. 验证已成功项的文件指纹（成功项不重试，但确认文件仍有效）
        for item in succeeded_items:
            if item.file_path and item.file_sha256:
                try:
                    from app.services.file_fingerprint_service import (
                        verify_file_fingerprint,
                    )
                    verify_file_fingerprint(
                        file_path=item.file_path,
                        expected_size=item.file_size,
                        expected_sha256=item.file_sha256,
                    )
                except Exception:
                    # 已成功项文件失效 → 也标记为需重试
                    logger.warning(
                        "[RETRY] 已成功项文件校验失败，降级为失败: item=%s step=%s",
                        item.id, item.step_key,
                    )
                    item.status = ExportJobItemStatus.failed.value
                    item.error_message = "文件指纹校验失败，需重新生成"
                    await self.db.flush()
                    failed_items.append(item)

        # 按 sequence 排序确保重试顺序正确
        failed_items.sort(key=lambda i: i.sequence or 0)

        # 6. 依次重试每个失败项
        snapshot_id = job.snapshot_id
        outcomes: list[dict] = []
        retried_count = 0
        succeeded_count = 0
        failed_count = 0

        # 重新获取所有 item 当前状态以做依赖检查
        item_status_map: dict[str, str] = {
            i.step_key: i.status for i in all_items if i.step_key
        }

        for item in failed_items:
            retried_count += 1

            # ── 依赖检查：audit_report 需要前两步成功 ──
            if item.step_key == "audit_report":
                dep_failed = [
                    dep for dep in AUDIT_REPORT_DEPENDENCIES
                    if item_status_map.get(dep) != ExportJobItemStatus.succeeded.value
                ]
                if dep_failed:
                    reason = (
                        f"前置步骤未成功（{', '.join(dep_failed)}），"
                        f"审计报告正文无法生成"
                    )
                    item.status = ExportJobItemStatus.blocked.value
                    item.error_message = reason
                    await self.db.flush()
                    item_status_map[item.step_key] = ExportJobItemStatus.blocked.value
                    failed_count += 1
                    outcomes.append({
                        "step": item.step_key,
                        "item_id": str(item.id),
                        "succeeded": False,
                        "error_message": reason,
                    })
                    continue

            # ── 创建新 attempt（保存点外，保留不可变历史）──
            new_attempt_no = item.attempt_count + 1
            attempt = ExportJobAttempt(
                job_id=job_id,
                item_id=item.id,
                attempt_no=new_attempt_no,
                status=ExportJobAttemptStatus.running.value,
                snapshot_id=snapshot_id,
                trigger_source="retry",
                started_at=datetime.now(timezone.utc),
            )
            self.db.add(attempt)
            item.attempt_count = new_attempt_no
            item.status = ExportJobItemStatus.running.value
            await self.db.flush()

            # ── 在 begin_nested() 保存点内执行步骤 ──
            try:
                async with self.db.begin_nested():
                    result = await step_runner.run_step(
                        item.step_key, snapshot_id,
                    )
                    # 成功：更新 item 和 attempt
                    item.status = ExportJobItemStatus.succeeded.value
                    item.error_message = None
                    item.last_attempt_id = attempt.id
                    item.finished_at = datetime.now(timezone.utc)
                    attempt.status = ExportJobAttemptStatus.succeeded.value
                    attempt.finished_at = datetime.now(timezone.utc)

                    # P0 fix: 从 word_export_task 回填文件元数据到 item
                    if isinstance(result, UUID):
                        from app.models.phase13_models import (
                            WordExportTask,
                            WordExportTaskVersion,
                        )
                        task_row = (await self.db.execute(
                            sa.select(WordExportTask).where(
                                WordExportTask.id == result,
                            )
                        )).scalar_one_or_none()
                        if task_row:
                            item.file_path = task_row.file_path
                            item.file_size = task_row.file_size
                            item.word_export_task_id = result
                            latest_ver = (await self.db.execute(
                                sa.select(WordExportTaskVersion)
                                .where(
                                    WordExportTaskVersion.word_export_task_id == result,
                                )
                                .order_by(WordExportTaskVersion.version_no.desc())
                                .limit(1)
                            )).scalar_one_or_none()
                            if latest_ver:
                                item.file_sha256 = latest_ver.file_hash
                                item.version_id = latest_ver.id

                    await self.db.flush()

                item_status_map[item.step_key] = ExportJobItemStatus.succeeded.value
                succeeded_count += 1
                outcomes.append({
                    "step": item.step_key,
                    "item_id": str(item.id),
                    "succeeded": True,
                    "attempt_no": new_attempt_no,
                })
            except Exception as exc:  # noqa: BLE001
                # 保存点已自动回滚业务写入
                # 在保存点外重新写入失败记录
                logger.warning(
                    "[RETRY] step=%s failed job=%s attempt=%d: %s",
                    item.step_key, job_id, new_attempt_no, exc,
                )
                now = datetime.now(timezone.utc)
                error_type = type(exc).__name__
                error_msg = str(exc)[:500] if str(exc) else "重试生成失败"
                diag = traceback.format_exception_only(type(exc), exc)
                diag_text = "".join(diag).strip()[:2000]

                # attempt 失败记录
                attempt.status = ExportJobAttemptStatus.failed.value
                attempt.finished_at = now
                attempt.error_type = error_type
                attempt.error_message = error_msg
                attempt.diagnostic_detail = diag_text

                # item 失败状态（保留原始失败原因在旧 attempt 中）
                item.status = ExportJobItemStatus.failed.value
                item.error_message = error_msg
                item.last_attempt_id = attempt.id
                item.finished_at = now
                await self.db.flush()

                item_status_map[item.step_key] = ExportJobItemStatus.failed.value
                failed_count += 1
                outcomes.append({
                    "step": item.step_key,
                    "item_id": str(item.id),
                    "succeeded": False,
                    "attempt_no": new_attempt_no,
                    "error_message": str(exc),
                })

        # 7. 重新聚合 job 状态和 trio_succeeded
        trio_statuses = [
            item_status_map[key]
            for key in ("financial_report", "disclosure_notes", "audit_report")
            if key in item_status_map
        ]
        job_status = aggregate_trio_status(trio_statuses)
        trio_succeeded = sum(
            1 for s in trio_statuses
            if s == ExportJobItemStatus.succeeded.value
        )

        job.status = job_status
        job.trio_succeeded = trio_succeeded
        job.finished_at = datetime.now(timezone.utc)
        await self.db.flush()

        logger.info(
            "retry_failed_trio: job=%s retried=%d succeeded=%d failed=%d trio=%d/3",
            job_id, retried_count, succeeded_count, failed_count, trio_succeeded,
        )

        return {
            "retried": retried_count,
            "succeeded": succeeded_count,
            "failed": failed_count,
            "skipped_succeeded": len(succeeded_items),
            "outcomes": outcomes,
            "job_status": job_status,
            "trio_succeeded": trio_succeeded,
        }


    # ------------------------------------------------------------------
    # Phase4 Task 7 — 不可变历史查询与 running 恢复
    # ------------------------------------------------------------------

    async def get_job_with_items(
        self,
        job_id: UUID,
    ) -> dict | None:
        """获取 job 详情 + items（含最新 attempt 信息）。

        返回 dict 而非 ORM 对象，便于直接序列化为 API 响应。
        需求 4.3 / 4.4 / 5.4。
        """
        job = await self.get_job(job_id)
        if job is None:
            return None

        # 获取 items 按 sequence 排序
        items_result = await self.db.execute(
            sa.select(ExportJobItem)
            .where(ExportJobItem.job_id == job_id)
            .order_by(ExportJobItem.sequence.asc().nullsfirst())
        )
        items = list(items_result.scalars().all())

        # 获取每个 item 的最新 attempt
        item_dicts = []
        for item in items:
            latest_attempt = None
            if item.last_attempt_id:
                attempt_result = await self.db.execute(
                    sa.select(ExportJobAttempt)
                    .where(ExportJobAttempt.id == item.last_attempt_id)
                )
                latest_attempt = attempt_result.scalar_one_or_none()

            item_dicts.append({
                "id": str(item.id),
                "job_id": str(item.job_id),
                "step_key": item.step_key,
                "sequence": item.sequence,
                "status": item.status,
                "error_message": item.error_message,
                "attempt_count": item.attempt_count,
                "last_attempt_id": str(item.last_attempt_id) if item.last_attempt_id else None,
                "snapshot_id": str(item.snapshot_id) if item.snapshot_id else None,
                "version_id": str(item.version_id) if item.version_id else None,
                "file_path": item.file_path,
                "file_size": item.file_size,
                "file_sha256": item.file_sha256,
                "finished_at": item.finished_at.isoformat() if item.finished_at else None,
                "latest_attempt": _attempt_to_dict(latest_attempt) if latest_attempt else None,
            })

        return {
            "id": str(job.id),
            "project_id": str(job.project_id),
            "job_type": job.job_type,
            "kind": job.kind,
            "status": job.status,
            "year": job.year,
            "trio_total": job.trio_total,
            "trio_succeeded": job.trio_succeeded,
            "snapshot_id": str(job.snapshot_id) if job.snapshot_id else None,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "items": item_dicts,
        }

    async def get_item_attempts(
        self,
        item_id: UUID,
    ) -> list[dict]:
        """获取某 item 的全部 attempt 历史，按 attempt_no 排序。

        需求 5.4：保留原始失败 attempt 和失败原因。
        """
        result = await self.db.execute(
            sa.select(ExportJobAttempt)
            .where(ExportJobAttempt.item_id == item_id)
            .order_by(ExportJobAttempt.attempt_no.asc())
        )
        attempts = list(result.scalars().all())
        return [_attempt_to_dict(a) for a in attempts]

    async def get_job_history(
        self,
        project_id: UUID,
        year: int,
    ) -> list[dict]:
        """获取项目/年度维度的全部 job 历史，按创建时间倒序。

        需求 4.4 / 5.6。
        """
        result = await self.db.execute(
            sa.select(ExportJob)
            .where(
                ExportJob.project_id == project_id,
                ExportJob.year == year,
                ExportJob.kind == "deliverable_trio",
            )
            .order_by(ExportJob.created_at.desc())
        )
        jobs = list(result.scalars().all())

        history = []
        for job in jobs:
            history.append({
                "id": str(job.id),
                "status": job.status,
                "trio_total": job.trio_total,
                "trio_succeeded": job.trio_succeeded,
                "snapshot_id": str(job.snapshot_id) if job.snapshot_id else None,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            })
        return history

    async def recover_stale_running(
        self,
        job_id: UUID,
        timeout_minutes: int = 30,
    ) -> dict:
        """中断/超时后的 running 恢复策略（fail-closed）。

        需求 4.6：下一次查询发现 running 超过阈值的 attempt/item，
        标记为 failed（中断/超时恢复）。绝不自动标记为 succeeded。

        Returns:
            dict with 'recovered_items' count and 'recovered_attempts' count.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)

        # 1. 找 stale running attempts（started_at < cutoff 且仍为 running）
        stale_attempts_result = await self.db.execute(
            sa.select(ExportJobAttempt)
            .where(
                ExportJobAttempt.job_id == job_id,
                ExportJobAttempt.status == ExportJobAttemptStatus.running.value,
                ExportJobAttempt.started_at < cutoff,
            )
        )
        stale_attempts = list(stale_attempts_result.scalars().all())

        now = datetime.now(timezone.utc)
        recovered_attempt_ids = set()
        recovered_item_ids = set()

        for attempt in stale_attempts:
            attempt.status = ExportJobAttemptStatus.failed.value
            attempt.finished_at = now
            attempt.error_type = "TimeoutRecovery"
            attempt.error_message = "中断/超时恢复：任务执行超时，已标记失败"
            attempt.diagnostic_detail = (
                f"attempt 启动于 {attempt.started_at.isoformat() if attempt.started_at else '未知'}，"
                f"超过 {timeout_minutes} 分钟未完成"
            )
            recovered_attempt_ids.add(attempt.id)
            recovered_item_ids.add(attempt.item_id)

        # 2. 找 stale running items（对应 attempt 已标记失败或无 running attempt）
        stale_items_result = await self.db.execute(
            sa.select(ExportJobItem)
            .where(
                ExportJobItem.job_id == job_id,
                ExportJobItem.status == ExportJobItemStatus.running.value,
            )
        )
        stale_items = list(stale_items_result.scalars().all())

        for item in stale_items:
            # 仅当 item 的创建时间（通过 attempt）已超阈值时标记失败
            # 或 item_id 已在 recovered_item_ids（其 attempt 已超时）
            if item.id in recovered_item_ids:
                item.status = ExportJobItemStatus.failed.value
                item.error_message = "中断/超时恢复：任务执行超时，已标记失败"

        # 3. 兜底：running item 无 attempt（极端崩溃场景）
        for item in stale_items:
            if item.id not in recovered_item_ids:
                has_attempt = await self.db.execute(
                    sa.select(sa.func.count()).select_from(ExportJobAttempt).where(
                        ExportJobAttempt.item_id == item.id,
                    )
                )
                if has_attempt.scalar_one() == 0:
                    item.status = ExportJobItemStatus.failed.value
                    item.error_message = "中断/超时恢复：任务无执行记录，已标记失败"
                    recovered_item_ids.add(item.id)

        # 3. 如果有恢复的 item，重新聚合 job 状态
        if recovered_item_ids or stale_items:
            from app.services.full_deliverables_executor import (
                TRIO_STEP_KEYS,
                aggregate_trio_status,
            )
            # 重新读取所有 items 计算 job 状态
            all_items_result = await self.db.execute(
                sa.select(ExportJobItem)
                .where(ExportJobItem.job_id == job_id)
            )
            all_items = list(all_items_result.scalars().all())

            trio_statuses = [
                i.status for i in all_items
                if i.step_key in TRIO_STEP_KEYS
            ]
            job_status = aggregate_trio_status(trio_statuses)
            trio_succeeded = sum(
                1 for s in trio_statuses
                if s == ExportJobItemStatus.succeeded.value
            )

            job = await self.get_job(job_id)
            if job:
                job.status = job_status
                job.trio_succeeded = trio_succeeded

        await self.db.flush()

        result = {
            "recovered_items": len(recovered_item_ids),
            "recovered_attempts": len(recovered_attempt_ids),
        }
        logger.info(
            "恢复 stale running: job_id=%s, items=%d, attempts=%d",
            job_id, result["recovered_items"], result["recovered_attempts"],
        )
        return result


def _attempt_to_dict(attempt: ExportJobAttempt) -> dict:
    """将 ExportJobAttempt ORM 对象转为 dict。"""
    return {
        "id": str(attempt.id),
        "job_id": str(attempt.job_id),
        "item_id": str(attempt.item_id),
        "attempt_no": attempt.attempt_no,
        "status": attempt.status,
        "started_at": attempt.started_at.isoformat() if attempt.started_at else None,
        "finished_at": attempt.finished_at.isoformat() if attempt.finished_at else None,
        "snapshot_id": str(attempt.snapshot_id) if attempt.snapshot_id else None,
        "error_type": attempt.error_type,
        "error_message": attempt.error_message,
        "diagnostic_detail": attempt.diagnostic_detail,
        "file_path": attempt.file_path,
        "file_size": attempt.file_size,
        "file_sha256": attempt.file_sha256,
        "version_id": str(attempt.version_id) if attempt.version_id else None,
        "trigger_source": attempt.trigger_source,
    }
