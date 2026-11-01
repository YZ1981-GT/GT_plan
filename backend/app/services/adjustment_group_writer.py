"""调整分录组唯一写入内核。

所有新建、整组替换、软删和恢复都必须同时维护 ``adjustments`` 与
``adjustment_entries``。本模块只 flush，不 commit，也不发布事件。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import (
    Adjustment,
    AdjustmentEntry,
    AdjustmentType,
    ReviewStatus,
)


@dataclass(frozen=True)
class AdjustmentGroupLine:
    standard_account_code: str
    account_name: str | None = None
    detail_account_code: str | None = None
    report_line_code: str | None = None
    debit_amount: Decimal = Decimal("0")
    credit_amount: Decimal = Decimal("0")


@dataclass(frozen=True)
class AdjustmentGroupWriteResult:
    adjustments: list[Adjustment]
    entries: list[AdjustmentEntry]


class AdjustmentGroupWriter:
    """同步维护调整重复头行与规范明细行。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def write_group(
        self,
        *,
        project_id: UUID,
        year: int,
        company_code: str,
        adjustment_no: str,
        adjustment_type: AdjustmentType,
        description: str | None,
        entry_group_id: UUID,
        lines: list[AdjustmentGroupLine],
        content_revision: int,
        audit_phase: str,
        review_status: ReviewStatus = ReviewStatus.draft,
        origin: str = "manual",
        source_ref: str | None = None,
        external_reference: str | None = None,
        import_batch_id: UUID | None = None,
        created_by: UUID,
        updated_by: UUID | None = None,
    ) -> AdjustmentGroupWriteResult:
        if not lines:
            raise ValueError("调整分录至少需要一条明细")
        if origin == "workpaper" and not source_ref:
            raise ValueError("底稿来源分录必须带 source_ref")
        if origin != "workpaper" and source_ref:
            raise ValueError("手工分录不得携带底稿 source_ref")
        adjustments: list[Adjustment] = []
        entries: list[AdjustmentEntry] = []
        for line_no, line in enumerate(lines, start=1):
            adjustment = Adjustment(
                project_id=project_id,
                year=year,
                company_code=company_code,
                adjustment_no=adjustment_no,
                adjustment_type=adjustment_type,
                description=description,
                account_code=line.standard_account_code,
                account_name=line.account_name,
                debit_amount=line.debit_amount,
                credit_amount=line.credit_amount,
                entry_group_id=entry_group_id,
                content_revision=content_revision,
                audit_phase=audit_phase,
                review_status=review_status,
                origin=origin,
                source_ref=source_ref,
                external_reference=(external_reference or "").strip() or None,
                import_batch_id=import_batch_id,
                created_by=created_by,
                updated_by=updated_by,
            )
            self.db.add(adjustment)
            await self.db.flush()
            entry = AdjustmentEntry(
                adjustment_id=adjustment.id,
                entry_group_id=entry_group_id,
                line_no=line_no,
                standard_account_code=line.standard_account_code,
                detail_account_code=line.detail_account_code,
                account_name=line.account_name,
                report_line_code=line.report_line_code,
                debit_amount=line.debit_amount,
                credit_amount=line.credit_amount,
            )
            self.db.add(entry)
            adjustments.append(adjustment)
            entries.append(entry)
        await self.db.flush()
        return AdjustmentGroupWriteResult(adjustments, entries)

    async def soft_delete_group(
        self,
        adjustments: list[Adjustment],
        entries: list[AdjustmentEntry],
        *,
        user_id: UUID | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        for row in adjustments:
            row.is_deleted = True
            row.deleted_at = now
            row.updated_by = user_id
        for row in entries:
            row.is_deleted = True
            row.deleted_at = now
        await self.db.flush()

    async def restore_by_adjustment_row_id(
        self,
        *,
        project_id: UUID,
        adjustment_row_id: UUID,
        user_id: UUID,
    ) -> UUID:
        """由回收站任一行恢复完整分录组，返回 entry_group_id。"""
        anchor = (await self.db.execute(
            sa.select(Adjustment).where(
                Adjustment.id == adjustment_row_id,
                Adjustment.project_id == project_id,
                Adjustment.is_deleted == sa.true(),
            )
        )).scalar_one_or_none()
        if anchor is None:
            raise ValueError("调整分录不存在或未被删除")
        group_rows = list((await self.db.execute(
            sa.select(Adjustment).where(
                Adjustment.project_id == project_id,
                Adjustment.entry_group_id == anchor.entry_group_id,
                Adjustment.is_deleted == sa.true(),
            )
        )).scalars().all())
        entry_rows = list((await self.db.execute(
            sa.select(AdjustmentEntry).where(
                AdjustmentEntry.entry_group_id == anchor.entry_group_id,
                AdjustmentEntry.is_deleted == sa.true(),
            )
        )).scalars().all())
        if not group_rows or not entry_rows:
            raise ValueError("调整分录组删除数据不完整，无法安全恢复")
        for row in group_rows:
            row.is_deleted = False
            row.deleted_at = None
            row.updated_by = user_id
        for row in entry_rows:
            row.is_deleted = False
            row.deleted_at = None
        await self.db.flush()
        return anchor.entry_group_id
