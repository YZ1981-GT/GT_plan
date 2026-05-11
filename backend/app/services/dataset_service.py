"""数据集版本服务 — 企业级账套版本治理

核心能力：
- 创建 staged 数据集
- 激活数据集（旧 active → superseded，新 staged → active）
- 回滚到上一版本
- 查询当前 active dataset_id
- 查询数据集历史
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset_models import (
    ActivationRecord,
    ActivationType,
    DatasetStatus,
    LedgerDataset,
)
from app.models.audit_platform_models import (
    AccountChart,
    TbAuxBalance,
    TbAuxLedger,
    TbBalance,
    TbLedger,
)


class DatasetIntegrityError(Exception):
    """F27 / Sprint 6.5: activate 前 integrity check 失败。

    触发条件：staged dataset 的四表物理行数与 ``record_summary`` 预期不符；
    原因通常是 pipeline 写入阶段并发冲突 / 磁盘错误 / 部分 commit 丢失。

    处理方式：事务回滚 + ImportJob.status 设为 integrity_check_failed
    （或 failed），通知用户重新 submit。
    """


class DatasetService:
    """数据集版本管理服务"""

    @staticmethod
    async def get_active_dataset_id(
        db: AsyncSession, project_id: UUID, year: int
    ) -> UUID | None:
        """获取当前 active 数据集 ID（核心查询方法）

        所有读路径应通过此方法获取当前有效版本，
        而非直接 WHERE is_deleted=false。
        """
        result = await db.execute(
            sa.select(LedgerDataset.id).where(
                LedgerDataset.project_id == project_id,
                LedgerDataset.year == year,
                LedgerDataset.status == DatasetStatus.active,
            ).order_by(LedgerDataset.activated_at.desc().nullslast(), LedgerDataset.created_at.desc())
        )
        row = result.scalars().first()
        return row

    @staticmethod
    async def _set_dataset_visibility(
        db: AsyncSession,
        *,
        project_id: UUID,
        year: int,
        dataset_id: UUID,
        is_deleted: bool,
    ) -> None:
        """[DEPRECATED B'] 不再对 4 张 Tb* 表做 UPDATE。

        保留方法签名是为了兼容可能的外部调用；实际架构下，数据可见性
        完全由 ledger_datasets.status 控制，物理行 is_deleted 恒为 false。
        """
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(
            "_set_dataset_visibility called but is no-op under B' architecture "
            "(dataset=%s, is_deleted=%s)",
            dataset_id, is_deleted,
        )

    @staticmethod
    async def cleanup_dataset_rows(db: AsyncSession, dataset_id: UUID) -> dict[str, int | None]:
        """Delete staged rows for a dataset that will never be activated."""
        deleted: dict[str, int | None] = {}
        for model in (TbBalance, TbLedger, TbAuxBalance, TbAuxLedger):
            tbl = model.__table__
            result = await db.execute(sa.delete(tbl).where(tbl.c.dataset_id == dataset_id))
            deleted[tbl.name] = result.rowcount
        ac = AccountChart.__table__
        result = await db.execute(sa.delete(ac).where(ac.c.dataset_id == dataset_id))
        deleted[ac.name] = result.rowcount
        return deleted

    @staticmethod
    async def create_staged(
        db: AsyncSession,
        project_id: UUID,
        year: int,
        source_type: str = "import",
        source_summary: dict | None = None,
        job_id: UUID | None = None,
        created_by: UUID | None = None,
    ) -> LedgerDataset:
        """创建 staged 数据集（导入写入前调用）"""
        # 查找当前 active 作为 previous
        current_active_id = await DatasetService.get_active_dataset_id(db, project_id, year)

        dataset = LedgerDataset(
            id=uuid.uuid4(),
            project_id=project_id,
            year=year,
            status=DatasetStatus.staged,
            source_type=source_type,
            source_summary=source_summary,
            job_id=job_id,
            previous_dataset_id=current_active_id,
            created_by=created_by,
        )
        db.add(dataset)
        await db.flush()
        return dataset

    @staticmethod
    async def activate(
        db: AsyncSession,
        dataset_id: UUID,
        activated_by: UUID | None = None,
        record_summary: dict | None = None,
        validation_summary: dict | None = None,
        *,
        ip_address: str | None = None,
        reason: str | None = None,
    ) -> LedgerDataset:
        """激活数据集：旧 active → superseded，新 staged → active

        这是原子操作，确保同一 project+year 只有一个 active。

        F25 / Sprint 10.7: 填充 ActivationRecord 审计字段
        (ip_address/duration_ms/before_row_counts/after_row_counts/reason)。
        """
        # F29 / Sprint 6.7: REPEATABLE READ 隔离级别（仅 PG 生效，SQLite 无等价）
        try:
            if "postgresql" in str(db.bind.url if hasattr(db, 'bind') else ''):
                await db.execute(sa.text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
        except Exception:
            pass  # SQLite 或连接池不支持时静默跳过

        started_at = datetime.now(timezone.utc)
        # 加载目标数据集
        result = await db.execute(
            sa.select(LedgerDataset).where(LedgerDataset.id == dataset_id)
        )
        dataset = result.scalar_one_or_none()
        if not dataset:
            raise ValueError(f"Dataset {dataset_id} not found")
        # F29 / Sprint 10.39: 幂等键——已是 active 的 dataset 再次 activate 直接返回成功
        # 场景：resume_from_checkpoint 重跑 activate 阶段 / 并发 retry
        if dataset.status == DatasetStatus.active:
            return dataset
        if dataset.status != DatasetStatus.staged:
            raise ValueError(f"Dataset {dataset_id} is not staged (current: {dataset.status})")

        # F27 / Sprint 6.4: 激活前 integrity check —— 核对 staged 物理行数
        # 与 record_summary 的预期一致。不一致 = 可能的静默数据损失，必须阻断。
        if record_summary:
            expected_counts = {
                k: v for k, v in record_summary.items()
                if k in ("tb_balance", "tb_ledger", "tb_aux_balance", "tb_aux_ledger")
                and isinstance(v, int)
            }
            if expected_counts:
                actual_counts = await DatasetService._row_counts_for_dataset(
                    db, dataset.id
                )
                mismatches = {
                    k: (expected_counts[k], actual_counts.get(k, 0))
                    for k in expected_counts
                    if expected_counts[k] != actual_counts.get(k, 0)
                }
                if mismatches:
                    # 构造详细错误信息，便于排查
                    detail = "; ".join(
                        f"{k}: expected={exp} actual={act}"
                        for k, (exp, act) in mismatches.items()
                    )
                    raise DatasetIntegrityError(
                        f"Dataset {dataset_id} integrity check failed: {detail}"
                    )

        # F25: 快照旧 active 的四表行数（激活前）— 只针对同 project + 同 year
        # F5 / Sprint 10.10: mark_previous_superseded 查询必须带 year 过滤，
        # 否则会跨年误标（2024 与 2025 双 active 时会把 2024 标 superseded）
        prev_active_result = await db.execute(
            sa.select(LedgerDataset.id).where(
                LedgerDataset.project_id == dataset.project_id,
                LedgerDataset.year == dataset.year,
                LedgerDataset.status == DatasetStatus.active,
            )
        )
        prev_active_id = prev_active_result.scalar_one_or_none()
        before_counts: dict | None = None
        if prev_active_id:
            before_counts = await DatasetService._row_counts_for_dataset(
                db, prev_active_id
            )

        # 将当前 active 标记为 superseded（严格按 project + year 过滤）
        await db.execute(
            sa.update(LedgerDataset).where(
                LedgerDataset.project_id == dataset.project_id,
                LedgerDataset.year == dataset.year,
                LedgerDataset.status == DatasetStatus.active,
            ).values(status=DatasetStatus.superseded)
        )
        # B' 架构：不再 UPDATE 物理行 is_deleted，可见性完全由 dataset.status 控制

        # 激活新数据集
        dataset.status = DatasetStatus.active
        dataset.activated_by = activated_by
        dataset.activated_at = datetime.now(timezone.utc)
        if record_summary:
            dataset.record_summary = record_summary
        if validation_summary:
            dataset.validation_summary = validation_summary
        # B' 架构：不再 UPDATE 物理行 is_deleted=False，新数据写入时已是 False

        # F25: 快照新 active 的四表行数（激活后）
        after_counts = await DatasetService._row_counts_for_dataset(db, dataset.id)
        duration_ms = int(
            (datetime.now(timezone.utc) - started_at).total_seconds() * 1000
        )

        # 记录激活操作
        record = ActivationRecord(
            id=uuid.uuid4(),
            project_id=dataset.project_id,
            year=dataset.year,
            dataset_id=dataset_id,
            action=ActivationType.activate,
            previous_dataset_id=dataset.previous_dataset_id,
            performed_by=activated_by,
            reason=reason or "导入完成自动激活",
            ip_address=ip_address,
            duration_ms=duration_ms,
            before_row_counts=before_counts,
            after_row_counts=after_counts,
        )
        db.add(record)

        # F53 / Sprint 8.40: 同步计算 retention_class + 写回 ImportArtifact
        # 失败不阻断激活主路径（保留期属于治理信息，不影响数据可见性）
        try:
            from app.services.ledger_import.retention_policy import (
                apply_retention_to_artifact,
            )

            await apply_retention_to_artifact(db, dataset)
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning(
                "retention_policy apply failed for dataset %s (non-fatal)",
                dataset_id,
                exc_info=True,
            )

        from app.models.audit_platform_schemas import EventType
        from app.services.import_event_outbox_service import ImportEventOutboxService

        outbox = await ImportEventOutboxService.enqueue(
            db,
            event_type=EventType.LEDGER_DATASET_ACTIVATED,
            project_id=dataset.project_id,
            year=dataset.year,
            payload={"dataset_id": str(dataset.id)},
        )
        setattr(dataset, "_activation_outbox_id", outbox.id)

        return dataset

    @staticmethod
    async def rollback(
        db: AsyncSession,
        project_id: UUID,
        year: int,
        performed_by: UUID | None = None,
        reason: str | None = None,
        ip_address: str | None = None,
    ) -> LedgerDataset | None:
        """回滚到上一版本

        当前 active → rolled_back，previous → active。
        如果没有 previous，返回 None。

        F23 / Sprint 5.14: activate 与 rollback 共享同一项目级锁，互斥执行。
        F25 / Sprint 5.18+5.20: 填充 ActivationRecord 审计字段
        (ip_address/duration_ms/before_row_counts/after_row_counts/reason)。
        """
        # F23: 获取项目级锁（activate/rollback 互斥）
        from app.services.import_queue_service import (  # 避免循环 import
            ImportLockError,
            ImportQueueService,
        )

        acquired = ImportQueueService.try_acquire_action_lock(
            project_id,
            action="rollback",
            user_id=str(performed_by) if performed_by else None,
        )
        if not acquired:
            raise ImportLockError(
                f"无法获取项目 {project_id} 的导入锁，可能有正在进行的 activate/import/rollback，请稍后重试",
                project_id=project_id,
                action="rollback",
            )
        started_at = datetime.now(timezone.utc)
        try:
            # 找到当前 active
            result = await db.execute(
                sa.select(LedgerDataset).where(
                    LedgerDataset.project_id == project_id,
                    LedgerDataset.year == year,
                    LedgerDataset.status == DatasetStatus.active,
                )
            )
            current = result.scalar_one_or_none()
            if not current:
                return None

            if not current.previous_dataset_id:
                return None  # 没有上一版本可回滚

            # F50 / Sprint 8.22: 合规关键保护
            # 当前 active 数据集一旦被 final/eqcr_approved 报表绑定，rollback 被拒
            # 解绑必须走 admin 双人授权 force-unbind 端点（Sprint 8.27）
            from app.models.report_models import AuditReport, ReportStatus

            bound_reports_result = await db.execute(
                sa.select(AuditReport.id, AuditReport.status, AuditReport.year)
                .where(
                    AuditReport.bound_dataset_id == current.id,
                    AuditReport.is_deleted == sa.false(),
                    AuditReport.status.in_(
                        (ReportStatus.final, ReportStatus.eqcr_approved)
                    ),
                )
            )
            bound_reports = bound_reports_result.all()
            if bound_reports:
                from fastapi import HTTPException

                raise HTTPException(
                    status_code=409,
                    detail={
                        "error_code": "SIGNED_REPORTS_BOUND",
                        "message": (
                            f"无法回滚：{len(bound_reports)} 份已定稿/EQCR 复核报表"
                            f"绑定此数据集，回滚会破坏签字合规性。"
                            f"如确需回滚，请使用 admin 双人授权 force-unbind 接口"
                        ),
                        "reports": [
                            {
                                "id": str(rid),
                                "status": (
                                    status.value if hasattr(status, "value") else str(status)
                                ),
                                "year": ryear,
                            }
                            for rid, status, ryear in bound_reports
                        ],
                        "dataset_id": str(current.id),
                    },
                )

            # 加载上一版本
            result = await db.execute(
                sa.select(LedgerDataset).where(
                    LedgerDataset.id == current.previous_dataset_id
                )
            )
            previous = result.scalar_one_or_none()
            if not previous:
                return None

            # F25: 快照当前 active 的四表行数（回滚前）
            before_counts = await DatasetService._row_counts_for_dataset(db, current.id)

            # 当前 → rolled_back
            current.status = DatasetStatus.rolled_back
            # B' 架构：不再 UPDATE 物理行 is_deleted，可见性完全由 dataset.status 控制

            # 上一版本 → active
            previous.status = DatasetStatus.active
            previous.activated_by = performed_by
            previous.activated_at = datetime.now(timezone.utc)
            # B' 架构：不再 UPDATE 物理行 is_deleted=False

            # F25: 快照恢复版本的四表行数（回滚后）
            after_counts = await DatasetService._row_counts_for_dataset(db, previous.id)

            duration_ms = int(
                (datetime.now(timezone.utc) - started_at).total_seconds() * 1000
            )

            # 记录回滚操作（任务 5.20：action='rollback' + F25 审计字段）
            record = ActivationRecord(
                id=uuid.uuid4(),
                project_id=project_id,
                year=year,
                dataset_id=previous.id,
                action=ActivationType.rollback,
                previous_dataset_id=current.id,
                performed_by=performed_by,
                reason=reason or "用户手动回滚",
                ip_address=ip_address,
                duration_ms=duration_ms,
                before_row_counts=before_counts,
                after_row_counts=after_counts,
            )
            db.add(record)
            setattr(previous, "_rolled_back_dataset_id", current.id)
            from app.models.audit_platform_schemas import EventType
            from app.services.import_event_outbox_service import ImportEventOutboxService

            outbox = await ImportEventOutboxService.enqueue(
                db,
                event_type=EventType.LEDGER_DATASET_ROLLED_BACK,
                project_id=project_id,
                year=year,
                payload={
                    # 保留历史键（多处消费方依赖）
                    "rolled_back_dataset_id": str(current.id),
                    "restored_dataset_id": str(previous.id),
                    # F46 / Sprint 7.21: 对齐 design D11.4 的载荷命名，
                    # 供下游 event_handlers._mark_downstream_stale_on_rollback 消费。
                    "project_id": str(project_id),
                    "year": year,
                    "old_dataset_id": str(current.id),
                    "new_active_dataset_id": str(previous.id),
                },
            )
            setattr(previous, "_rollback_outbox_id", outbox.id)

            return previous
        finally:
            ImportQueueService.release_action_lock(project_id)

    @staticmethod
    async def _row_counts_for_dataset(
        db: AsyncSession, dataset_id: UUID
    ) -> dict[str, int]:
        """F25 审计辅助：按 dataset_id 统计四张 Tb* 表的物理行数。

        只按 dataset_id 过滤，不过滤 is_deleted（B' 架构下物理行均 is_deleted=false，
        按 dataset_id 即可定位）。老数据 dataset_id 可能为 NULL，返回 0 即可。
        """
        counts: dict[str, int] = {}
        for model in (TbBalance, TbLedger, TbAuxBalance, TbAuxLedger):
            tbl = model.__table__
            result = await db.execute(
                sa.select(sa.func.count())
                .select_from(tbl)
                .where(tbl.c.dataset_id == dataset_id)
            )
            counts[tbl.name] = int(result.scalar_one() or 0)
        return counts

    @staticmethod
    async def publish_dataset_activated(dataset: LedgerDataset) -> None:
        """Publish activation after the transaction has committed."""
        outbox_id = getattr(dataset, "_activation_outbox_id", None)
        if outbox_id:
            from app.core.database import async_session
            from app.services.import_event_outbox_service import ImportEventOutboxService

            async with async_session() as db:
                await ImportEventOutboxService.publish_one(db, outbox_id)
                await db.commit()
            return
        try:
            from app.services.event_bus import event_bus
            from app.models.audit_platform_schemas import EventPayload, EventType
            await event_bus.publish(EventPayload(
                event_type=EventType.LEDGER_DATASET_ACTIVATED,
                project_id=dataset.project_id,
                year=dataset.year,
                extra={"dataset_id": str(dataset.id)},
            ))
        except Exception:
            pass

    @staticmethod
    async def publish_dataset_rolled_back(
        *,
        project_id: UUID,
        year: int,
        rolled_back_dataset_id: UUID,
        restored_dataset_id: UUID,
    ) -> None:
        """Publish rollback after the transaction has committed."""
        try:
            from app.services.event_bus import event_bus
            from app.models.audit_platform_schemas import EventPayload, EventType
            await event_bus.publish(EventPayload(
                event_type=EventType.LEDGER_DATASET_ROLLED_BACK,
                project_id=project_id,
                year=year,
                extra={
                    "rolled_back_dataset_id": str(rolled_back_dataset_id),
                    "restored_dataset_id": str(restored_dataset_id),
                },
            ))
        except Exception:
            pass

    @staticmethod
    async def publish_dataset_rolled_back_from_record(dataset: LedgerDataset) -> None:
        outbox_id = getattr(dataset, "_rollback_outbox_id", None)
        if outbox_id:
            from app.core.database import async_session
            from app.services.import_event_outbox_service import ImportEventOutboxService

            async with async_session() as db:
                await ImportEventOutboxService.publish_one(db, outbox_id)
                await db.commit()
            return
        rolled_back_dataset_id = getattr(dataset, "_rolled_back_dataset_id", None)
        if rolled_back_dataset_id:
            await DatasetService.publish_dataset_rolled_back(
                project_id=dataset.project_id,
                year=dataset.year,
                rolled_back_dataset_id=rolled_back_dataset_id,
                restored_dataset_id=dataset.id,
            )

    @staticmethod
    async def mark_failed(db: AsyncSession, dataset_id: UUID, *, cleanup_rows: bool = True) -> None:
        """标记数据集为失败（导入过程中出错时调用）"""
        cleanup_summary = await DatasetService.cleanup_dataset_rows(db, dataset_id) if cleanup_rows else None
        values = {"status": DatasetStatus.failed}
        if cleanup_summary is not None:
            values["record_summary"] = {"cleanup_deleted_rows": cleanup_summary}
        await db.execute(
            sa.update(LedgerDataset).where(
                LedgerDataset.id == dataset_id
            ).values(**values)
        )

    @staticmethod
    async def mark_failed_for_job(db: AsyncSession, job_id: UUID) -> int:
        """Mark staged datasets produced by a timed-out job as failed and clean rows."""
        result = await db.execute(
            sa.select(LedgerDataset.id).where(
                LedgerDataset.job_id == job_id,
                LedgerDataset.status == DatasetStatus.staged,
            )
        )
        dataset_ids = list(result.scalars().all())
        for dataset_id in dataset_ids:
            await DatasetService.mark_failed(db, dataset_id)
        return len(dataset_ids)

    @staticmethod
    async def list_datasets(
        db: AsyncSession, project_id: UUID, year: int
    ) -> list[LedgerDataset]:
        """查询数据集历史（按创建时间倒序）"""
        result = await db.execute(
            sa.select(LedgerDataset).where(
                LedgerDataset.project_id == project_id,
                LedgerDataset.year == year,
            ).order_by(LedgerDataset.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_activation_records(
        db: AsyncSession, project_id: UUID, year: int
    ) -> list[ActivationRecord]:
        """查询激活/回滚历史"""
        result = await db.execute(
            sa.select(ActivationRecord).where(
                ActivationRecord.project_id == project_id,
                ActivationRecord.year == year,
            ).order_by(ActivationRecord.performed_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def purge_old_datasets(
        db: AsyncSession,
        project_id: UUID,
        *,
        year: int | None = None,
        keep_count: int = 3,
    ) -> dict:
        """F3 / F50 / F53：清理 superseded 旧数据集，保留最近 N 个。

        保留策略（多层级过滤，都不会动 active/staged/rolled_back/failed）：
        - 同一 (project_id, year) 下最多保留 ``keep_count`` 个 superseded（按 created_at DESC）
        - 超出的 superseded 先经过两道合规过滤：
          1. **F50 / 下游绑定**：被 Workpaper / AuditReport / DisclosureNote /
             UnadjustedMisstatement 通过 ``bound_dataset_id`` 引用的 dataset 永不删
             （记为 ``skipped_due_to_binding``）。合规关键：签字后的报表引用的
             数据集必须永久保留。
          2. **F53 / retention class**：dataset 对应的 ImportArtifact 若
             ``retention_class`` ∈ {archived, legal_hold} 也永不物理删
             （记为 ``skipped_due_to_retention``）。仅 ``transient`` 过期后才删。
        - 过滤后仍需要删的才 ``cleanup_dataset_rows`` 物理删 Tb* 行、删除
          ``LedgerDataset`` + ``ActivationRecord`` 记录。

        ``rolled_back`` 保留作为 UAT 审计证据；``failed`` 由 ``mark_failed``
        自身清理（记录保留以便排查）。

        Args:
            db: 异步 session
            project_id: 目标项目
            year: 可选，限定某年度；None 则扫所有年度
            keep_count: 保留最近 superseded 数量（默认 3）

        Returns:
            ``{"years_processed": N, "datasets_deleted": M, "rows_cleaned": {...},
               "skipped_due_to_binding": X, "skipped_due_to_retention": Y}``
        """
        if keep_count < 0:
            raise ValueError(f"keep_count must be >= 0, got {keep_count}")

        # 延迟 import 以避免循环依赖
        from app.models.dataset_models import ImportArtifact, ImportJob
        from app.models.report_models import AuditReport, DisclosureNote
        from app.models.workpaper_models import WorkingPaper
        from app.models.audit_platform_models import UnadjustedMisstatement

        # 收集所有年度（只扫有 superseded 的年度）
        year_filters = [LedgerDataset.project_id == project_id]
        if year is not None:
            year_filters.append(LedgerDataset.year == year)

        year_rows = (
            await db.execute(
                sa.select(LedgerDataset.year)
                .where(*year_filters)
                .group_by(LedgerDataset.year)
            )
        ).scalars().all()

        years_to_process = list(year_rows)
        datasets_deleted = 0
        skipped_due_to_binding = 0
        skipped_due_to_retention = 0
        total_rows_cleaned: dict[str, int] = {}

        # 四张下游表——任一命中就判为"被绑定"不可删
        _bound_tables = (
            (WorkingPaper, "WorkingPaper"),
            (AuditReport, "AuditReport"),
            (DisclosureNote, "DisclosureNote"),
            (UnadjustedMisstatement, "UnadjustedMisstatement"),
        )

        for yr in years_to_process:
            # 按年度查 superseded，created_at DESC
            ss_result = await db.execute(
                sa.select(LedgerDataset)
                .where(
                    LedgerDataset.project_id == project_id,
                    LedgerDataset.year == yr,
                    LedgerDataset.status == DatasetStatus.superseded,
                )
                .order_by(LedgerDataset.created_at.desc())
            )
            ss_datasets = list(ss_result.scalars().all())

            # 超过 keep_count 的尾部作为候选删除集
            to_consider = ss_datasets[keep_count:]
            if not to_consider:
                continue

            for ds in to_consider:
                # ---- F50：检查下游绑定 ----
                is_bound = False
                for model, _name in _bound_tables:
                    count_res = await db.execute(
                        sa.select(sa.func.count())
                        .select_from(model)
                        .where(model.bound_dataset_id == ds.id)
                    )
                    if int(count_res.scalar_one() or 0) > 0:
                        is_bound = True
                        break
                if is_bound:
                    skipped_due_to_binding += 1
                    continue

                # ---- F53：检查 retention_class ----
                # 没有 job_id 或没有 artifact 的老数据集直接按 transient 处理
                retention_class_val = "transient"
                if ds.job_id is not None:
                    art_res = await db.execute(
                        sa.select(ImportArtifact.retention_class)
                        .select_from(ImportArtifact)
                        .join(ImportJob, ImportJob.artifact_id == ImportArtifact.id)
                        .where(ImportJob.id == ds.job_id)
                    )
                    rc = art_res.scalar_one_or_none()
                    if isinstance(rc, str) and rc:
                        retention_class_val = rc
                if retention_class_val in ("archived", "legal_hold"):
                    skipped_due_to_retention += 1
                    continue

                # ---- 真正执行删除 ----
                cleanup = await DatasetService.cleanup_dataset_rows(db, ds.id)
                for k, v in cleanup.items():
                    if isinstance(v, int):
                        total_rows_cleaned[k] = total_rows_cleaned.get(k, 0) + v

                # 删除关联 ActivationRecord
                await db.execute(
                    sa.delete(ActivationRecord).where(
                        ActivationRecord.dataset_id == ds.id
                    )
                )
                # 删除 LedgerDataset 元数据行
                await db.execute(
                    sa.delete(LedgerDataset).where(LedgerDataset.id == ds.id)
                )
                datasets_deleted += 1

        return {
            "years_processed": len(years_to_process),
            "datasets_deleted": datasets_deleted,
            "rows_cleaned": total_rows_cleaned,
            "skipped_due_to_binding": skipped_due_to_binding,
            "skipped_due_to_retention": skipped_due_to_retention,
        }

    @staticmethod
    async def purge_all_projects(
        db: AsyncSession, *, keep_count: int = 3
    ) -> dict:
        """扫所有项目执行 purge_old_datasets，供定时 worker 调用。"""
        project_ids = (
            await db.execute(
                sa.select(LedgerDataset.project_id)
                .where(LedgerDataset.status == DatasetStatus.superseded)
                .group_by(LedgerDataset.project_id)
            )
        ).scalars().all()

        summary: dict = {
            "projects_processed": 0,
            "datasets_deleted": 0,
            "rows_cleaned": {},
            "skipped_due_to_binding": 0,
            "skipped_due_to_retention": 0,
        }
        for pid in project_ids:
            out = await DatasetService.purge_old_datasets(
                db, pid, keep_count=keep_count
            )
            await db.commit()
            summary["projects_processed"] += 1
            summary["datasets_deleted"] += out["datasets_deleted"]
            summary["skipped_due_to_binding"] += out.get("skipped_due_to_binding", 0)
            summary["skipped_due_to_retention"] += out.get("skipped_due_to_retention", 0)
            for k, v in out["rows_cleaned"].items():
                summary["rows_cleaned"][k] = (
                    summary["rows_cleaned"].get(k, 0) + v
                )
        return summary
