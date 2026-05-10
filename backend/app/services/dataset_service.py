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
    AccountSource,
    TbAuxBalance,
    TbAuxLedger,
    TbBalance,
    TbLedger,
)


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
        """Toggle physical row visibility for a dataset during activate/rollback.

        B3 实测记录（2026-05-10）：YG2101 级 200 万行 UPDATE 串行 127s；
        曾试 asyncio.gather + 独立 session 并行 4 张表，无效（126s）——PG WAL 写入
        串行是瓶颈，不是 Python 侧。真正加速走 partial index on (dataset_id)
        WHERE is_deleted=true，让 UPDATE 的 WHERE 子句走索引。
        """
        for model in (TbBalance, TbLedger, TbAuxBalance, TbAuxLedger):
            tbl = model.__table__
            await db.execute(
                sa.update(tbl)
                .where(
                    tbl.c.project_id == project_id,
                    tbl.c.year == year,
                    tbl.c.dataset_id == dataset_id,
                )
                .values(is_deleted=is_deleted)
            )
        ac = AccountChart.__table__
        await db.execute(
            sa.update(ac)
            .where(
                ac.c.project_id == project_id,
                ac.c.source == AccountSource.client,
                ac.c.dataset_id == dataset_id,
            )
            .values(is_deleted=is_deleted)
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
    ) -> LedgerDataset:
        """激活数据集：旧 active → superseded，新 staged → active

        这是原子操作，确保同一 project+year 只有一个 active。
        """
        # 加载目标数据集
        result = await db.execute(
            sa.select(LedgerDataset).where(LedgerDataset.id == dataset_id)
        )
        dataset = result.scalar_one_or_none()
        if not dataset:
            raise ValueError(f"Dataset {dataset_id} not found")
        if dataset.status != DatasetStatus.staged:
            raise ValueError(f"Dataset {dataset_id} is not staged (current: {dataset.status})")

        # 将当前 active 标记为 superseded
        await db.execute(
            sa.update(LedgerDataset).where(
                LedgerDataset.project_id == dataset.project_id,
                LedgerDataset.year == dataset.year,
                LedgerDataset.status == DatasetStatus.active,
            ).values(status=DatasetStatus.superseded)
        )
        if dataset.previous_dataset_id:
            await DatasetService._set_dataset_visibility(
                db,
                project_id=dataset.project_id,
                year=dataset.year,
                dataset_id=dataset.previous_dataset_id,
                is_deleted=True,
            )

        # 激活新数据集
        dataset.status = DatasetStatus.active
        dataset.activated_by = activated_by
        dataset.activated_at = datetime.now(timezone.utc)
        if record_summary:
            dataset.record_summary = record_summary
        if validation_summary:
            dataset.validation_summary = validation_summary
        await DatasetService._set_dataset_visibility(
            db,
            project_id=dataset.project_id,
            year=dataset.year,
            dataset_id=dataset.id,
            is_deleted=False,
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
            reason="导入完成自动激活",
        )
        db.add(record)
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
    ) -> LedgerDataset | None:
        """回滚到上一版本

        当前 active → rolled_back，previous → active。
        如果没有 previous，返回 None。
        """
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

        # 加载上一版本
        result = await db.execute(
            sa.select(LedgerDataset).where(
                LedgerDataset.id == current.previous_dataset_id
            )
        )
        previous = result.scalar_one_or_none()
        if not previous:
            return None

        # 当前 → rolled_back
        current.status = DatasetStatus.rolled_back
        await DatasetService._set_dataset_visibility(
            db,
            project_id=project_id,
            year=year,
            dataset_id=current.id,
            is_deleted=True,
        )

        # 上一版本 → active
        previous.status = DatasetStatus.active
        previous.activated_by = performed_by
        previous.activated_at = datetime.now(timezone.utc)
        await DatasetService._set_dataset_visibility(
            db,
            project_id=project_id,
            year=year,
            dataset_id=previous.id,
            is_deleted=False,
        )

        # 记录回滚操作
        record = ActivationRecord(
            id=uuid.uuid4(),
            project_id=project_id,
            year=year,
            dataset_id=previous.id,
            action=ActivationType.rollback,
            previous_dataset_id=current.id,
            performed_by=performed_by,
            reason=reason or "用户手动回滚",
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
                "rolled_back_dataset_id": str(current.id),
                "restored_dataset_id": str(previous.id),
            },
        )
        setattr(previous, "_rollback_outbox_id", outbox.id)

        return previous

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
