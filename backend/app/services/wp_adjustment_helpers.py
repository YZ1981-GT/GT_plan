"""调整分录计数共享 helper

统一 _count_adjustments / _count_adjustments_with_pending 实现，
消除 auto_data_resolvers.py 和 procedure_table_auto_service.py 重复。
"""
from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession


async def count_adjustment_groups(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    *,
    adjustment_type: str | None = None,
    review_statuses: tuple[str, ...] | None = None,
    passed_only: bool = False,
) -> int:
    """按 ``entry_group_id`` 统计业务分录组；passed_only 改读正式错报表。"""
    from app.models.audit_platform_models import Adjustment, UnadjustedMisstatement

    if passed_only:
        stmt = sa.select(sa.func.count()).select_from(UnadjustedMisstatement).where(
            UnadjustedMisstatement.project_id == project_id,
            UnadjustedMisstatement.year == year,
            UnadjustedMisstatement.is_deleted == sa.false(),
            UnadjustedMisstatement.prior_year_status != "reversed",
        )
        return int((await db.execute(stmt)).scalar() or 0)

    stmt = sa.select(sa.func.count(sa.distinct(Adjustment.entry_group_id))).where(
        Adjustment.project_id == project_id,
        Adjustment.year == year,
        Adjustment.is_deleted == sa.false(),
    )
    if adjustment_type is not None:
        stmt = stmt.where(Adjustment.adjustment_type == adjustment_type)
    if review_statuses:
        stmt = stmt.where(Adjustment.review_status.in_(review_statuses))
    result = await db.execute(stmt)
    return int(result.scalar() or 0)


async def count_unresolved_adjustment_groups(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    *,
    adjustment_type: str | None = None,
) -> int:
    """统计尚未全组批准的分录组。

    内部驳回与管理层不更正是两个状态轴；正式错报记录不能让未完成内部复核的
    分录从待处理统计中消失。
    """
    from app.models.audit_platform_models import Adjustment, ReviewStatus

    grouped = (
        sa.select(
            Adjustment.entry_group_id.label("entry_group_id"),
            sa.func.min(sa.case(
                (Adjustment.review_status == ReviewStatus.approved, 1), else_=0,
            )).label("all_approved"),
        )
        .where(
            Adjustment.project_id == project_id,
            Adjustment.year == year,
            Adjustment.is_deleted == sa.false(),
        )
    )
    if adjustment_type is not None:
        grouped = grouped.where(Adjustment.adjustment_type == adjustment_type)
    grouped_sq = grouped.group_by(Adjustment.entry_group_id).subquery()
    result = await db.execute(
        sa.select(sa.func.count()).select_from(grouped_sq).where(
            grouped_sq.c.all_approved == 0,
        )
    )
    return int(result.scalar() or 0)


async def count_adjustments(
    db: AsyncSession, project_id: UUID, year: int, adj_type: str
) -> int:
    """按类型统计调整分录笔数（按 ``entry_group_id`` 去重）。"""
    if adj_type == "passed":
        return await count_adjustment_groups(
            db, project_id, year, passed_only=True,
        )
    return await count_adjustment_groups(
        db, project_id, year, adjustment_type=adj_type,
    )


async def count_adjustments_with_pending(
    db: AsyncSession, project_id: UUID, year: int, adj_type: str
) -> tuple[int, int, float]:
    """返回分录组总数、待处理组数与逐明细行借方金额合计。"""
    from app.models.audit_platform_models import Adjustment, AdjustmentEntry

    total = await count_adjustment_groups(
        db, project_id, year, adjustment_type=adj_type,
    )
    pending = await count_unresolved_adjustment_groups(
        db, project_id, year, adjustment_type=adj_type,
    )

    # 金额是行级可加事实，必须保留 SUM；只排除已软删的两侧明细。
    amount_stmt = (
        sa.select(sa.func.coalesce(sa.func.sum(AdjustmentEntry.debit_amount), 0))
        .join(Adjustment, AdjustmentEntry.adjustment_id == Adjustment.id)
        .where(
            Adjustment.project_id == project_id,
            Adjustment.year == year,
            Adjustment.adjustment_type == adj_type,
            Adjustment.is_deleted == sa.false(),
            AdjustmentEntry.is_deleted == sa.false(),
        )
    )
    amount = (await db.execute(amount_stmt)).scalar() or 0
    return total, pending, float(amount)
