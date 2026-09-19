"""调整分录计数共享 helper

统一 _count_adjustments / _count_adjustments_with_pending 实现，
消除 auto_data_resolvers.py 和 procedure_table_auto_service.py 重复。
"""
from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession


async def count_adjustments(
    db: AsyncSession, project_id: UUID, year: int, adj_type: str
) -> int:
    """按类型统计调整分录数。

    Args:
        db: 异步数据库会话
        project_id: 项目 ID
        year: 审计年度
        adj_type: 调整类型，可选值为 "aje" | "rje" | "passed"
            - "aje": 审计调整分录
            - "rje": 重分类调整分录
            - "passed": 未更正错报（passed_reason IS NOT NULL）

    Returns:
        满足条件的调整分录总数
    """
    from app.models.audit_platform_models import Adjustment

    if adj_type == "passed":
        # 未更正错报：passed_reason 非空表示管理层不予更正
        stmt = (
            sa.select(sa.func.count())
            .select_from(Adjustment)
            .where(
                Adjustment.project_id == project_id,
                Adjustment.year == year,
                Adjustment.passed_reason.isnot(None),
                Adjustment.is_deleted == sa.false(),
            )
        )
    else:
        stmt = (
            sa.select(sa.func.count())
            .select_from(Adjustment)
            .where(
                Adjustment.project_id == project_id,
                Adjustment.year == year,
                Adjustment.adjustment_type == adj_type,
                Adjustment.is_deleted == sa.false(),
            )
        )
    result = await db.execute(stmt)
    return result.scalar() or 0


async def count_adjustments_with_pending(
    db: AsyncSession, project_id: UUID, year: int, adj_type: str
) -> tuple[int, int, float]:
    """按类型统计调整分录：总数、待审批数、借方总金额。

    Args:
        db: 异步数据库会话
        project_id: 项目 ID
        year: 审计年度
        adj_type: 调整类型，可选值为 "aje" | "rje"

    Returns:
        三元组 (total, pending, debit_amount):
            - total: 该类型调整分录总数
            - pending: 待审批数（review_status != 'approved' 且 passed_reason 为空）
            - debit_amount: 借方合计金额（float，衡量调整影响规模）
    """
    from app.models.audit_platform_models import Adjustment, AdjustmentEntry

    total_stmt = (
        sa.select(sa.func.count())
        .select_from(Adjustment)
        .where(
            Adjustment.project_id == project_id,
            Adjustment.year == year,
            Adjustment.adjustment_type == adj_type,
            Adjustment.is_deleted == sa.false(),
        )
    )
    pending_stmt = (
        sa.select(sa.func.count())
        .select_from(Adjustment)
        .where(
            Adjustment.project_id == project_id,
            Adjustment.year == year,
            Adjustment.adjustment_type == adj_type,
            Adjustment.review_status != "approved",
            Adjustment.passed_reason.is_(None),
            Adjustment.is_deleted == sa.false(),
        )
    )
    # 借方合计金额（衡量调整影响规模）
    amount_stmt = (
        sa.select(sa.func.coalesce(sa.func.sum(AdjustmentEntry.debit_amount), 0))
        .join(Adjustment, AdjustmentEntry.adjustment_id == Adjustment.id)
        .where(
            Adjustment.project_id == project_id,
            Adjustment.year == year,
            Adjustment.adjustment_type == adj_type,
            Adjustment.is_deleted == sa.false(),
        )
    )

    total_r = await db.execute(total_stmt)
    pending_r = await db.execute(pending_stmt)
    amount_r = await db.execute(amount_stmt)
    return (total_r.scalar() or 0, pending_r.scalar() or 0, float(amount_r.scalar() or 0))
