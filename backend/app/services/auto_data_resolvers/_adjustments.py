"""调整分录 / 错报评价 / 重要性 / 试算平衡 域 resolvers。"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auto_data_resolvers import auto_resolver

from app.services.wp_adjustment_helpers import count_adjustments, count_adjustments_with_pending


@auto_resolver("adjustment_count_aje")
async def _resolve_adj_aje(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """审计调整分录（AJE）数量及金额汇总。

    数据来源: adjustment / adjustment_entry 表（通过 wp_adjustment_helpers）
    返回结构: {"summary": str}
    """
    count, pending, amount = await count_adjustments_with_pending(db, project_id, year, "aje")
    if count == 0:
        return {"summary": "无"}
    if pending > 0:
        return {"summary": f"共{count}笔 ¥{amount:,.0f}（⚠️{pending}笔待审）"}
    return {"summary": f"共{count}笔 ¥{amount:,.0f}（全部已批）"}


@auto_resolver("adjustment_count_rje")
async def _resolve_adj_rje(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """重分类调整分录（RJE）数量及金额汇总。

    数据来源: adjustment / adjustment_entry 表（通过 wp_adjustment_helpers）
    返回结构: {"summary": str}
    """
    count, pending, amount = await count_adjustments_with_pending(db, project_id, year, "rje")
    if count == 0:
        return {"summary": "无"}
    if pending > 0:
        return {"summary": f"共{count}笔 ¥{amount:,.0f}（⚠️{pending}笔待审）"}
    return {"summary": f"共{count}笔 ¥{amount:,.0f}（全部已批）"}


@auto_resolver("adjustment_count_passed")
async def _resolve_adj_passed(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """未更正错报（Passed Adjustments）数量统计。

    数据来源: adjustment 表（passed_reason IS NOT NULL，通过 wp_adjustment_helpers）
    返回结构: {"summary": str}
    """
    count = await count_adjustments(db, project_id, year, "passed")
    return {"summary": f"共{count}笔" if count else "无"}


@auto_resolver("adjustment_count_consol")
async def _resolve_adj_consol(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """合并调整分录数量统计。

    数据来源: elimination_entry 表
    返回结构: {"summary": str}
    """
    from app.models.consolidation_models import EliminationEntry
    stmt = sa.select(sa.func.count()).select_from(EliminationEntry).where(
        EliminationEntry.project_id == project_id,
        EliminationEntry.is_deleted == sa.false(),
    )
    r = await db.execute(stmt)
    count = r.scalar() or 0
    return {"summary": f"共{count}笔合并调整" if count else "无合并调整"}


@auto_resolver("misstatement_summary")
async def _resolve_misstatement_summary(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """未更正错报笔数摘要（A13 评价错报用）。

    数据来源: adjustment 表（passed_reason IS NOT NULL，通过 wp_adjustment_helpers）
    返回结构: {"summary": str}
    """
    count = await count_adjustments(db, project_id, year, "passed")
    return {"summary": f"未更正错报{count}笔" if count else "无未更正错报"}


@auto_resolver("misstatement_evaluation")
async def _resolve_misstatement_eval(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """未更正错报与重要性水平对比评价（A13 错报评价用）。

    数据来源: adjustment / adjustment_entry / materiality 表
    返回结构: {"summary": str}（含错报金额与执行重要性/明显微小阈值比较结论）
    """
    from app.models.audit_platform_models import Adjustment, Materiality, AdjustmentEntry
    passed_stmt = sa.select(
        sa.func.coalesce(sa.func.sum(AdjustmentEntry.debit_amount), 0)
    ).join(
        Adjustment, AdjustmentEntry.adjustment_id == Adjustment.id
    ).where(
        Adjustment.project_id == project_id,
        Adjustment.year == year,
        Adjustment.passed_reason.isnot(None),
        Adjustment.is_deleted == sa.false(),
    )
    passed_r = await db.execute(passed_stmt)
    passed_amount = passed_r.scalar() or 0
    mat_stmt = sa.select(Materiality.performance_materiality, Materiality.trivial_threshold).where(
        Materiality.project_id == project_id,
    )
    mat_r = await db.execute(mat_stmt)
    mat_row = mat_r.first()
    if not mat_row or not mat_row.performance_materiality:
        return {"summary": f"未更正错报 ¥{passed_amount:,.0f}（重要性待设置）"}
    perf_mat = float(mat_row.performance_materiality)
    trivial = float(mat_row.trivial_threshold) if mat_row.trivial_threshold else 0
    if passed_amount == 0:
        return {"summary": "无未更正错报"}
    if passed_amount > perf_mat:
        return {"summary": f"⚠️ 未更正错报 ¥{passed_amount:,.0f} 超执行重要性 ¥{perf_mat:,.0f}"}
    if passed_amount <= trivial:
        return {"summary": f"未更正错报 ¥{passed_amount:,.0f}，低于明显微小阈值 → 不影响意见"}
    return {"summary": f"未更正错报 ¥{passed_amount:,.0f}，低于执行重要性 ¥{perf_mat:,.0f}"}


# ═══════════════════════════════════════════════════════════════════════════════
# 重要性 / 试算平衡 / 合并
# ═══════════════════════════════════════════════════════════════════════════════


@auto_resolver("materiality_set")
async def _resolve_materiality(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """整体重要性水平数值（简略版，仅返回 overall_materiality）。

    数据来源: materiality 表
    返回结构: {"summary": str}
    """
    from app.models.audit_platform_models import Materiality
    stmt = sa.select(Materiality.overall_materiality).where(Materiality.project_id == project_id)
    result = await db.execute(stmt)
    val = result.scalar_one_or_none()
    mat = Decimal(str(val)) if val else Decimal("0")
    return {"summary": f"重要性水平 {mat:,.0f} 元" if mat else "待设置"}


@auto_resolver("trial_balance_check")
async def _resolve_tb_check(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """试算平衡验证（借方合计 vs 贷方合计差异检查）。

    数据来源: tb_balance 表（level=1 汇总行）
    返回结构: {"summary": str}（含借贷方金额及平衡/不平衡状态）
    """
    from app.models.audit_platform_models import TbBalance
    from app.services.dataset_query import get_active_filter
    tb = TbBalance.__table__
    active_filter = await get_active_filter(db, tb, project_id, year)
    bal_stmt = sa.select(
        sa.func.coalesce(
            sa.func.sum(sa.case((tb.c.closing_balance > 0, tb.c.closing_balance), else_=sa.literal(0))), 0
        ).label("debit_total"),
        sa.func.coalesce(
            sa.func.sum(sa.case((tb.c.closing_balance < 0, sa.func.abs(tb.c.closing_balance)), else_=sa.literal(0))), 0
        ).label("credit_total"),
    ).where(active_filter, tb.c.level == 1)
    bal_r = await db.execute(bal_stmt)
    bal_row = bal_r.first()
    if bal_row:
        debit = float(bal_row.debit_total)
        credit = float(bal_row.credit_total)
        diff = abs(debit - credit)
        if diff < 0.01:
            return {"summary": f"✓ 试算平衡（借=贷 ¥{debit:,.0f}）"}
        return {"summary": f"⚠️ 不平衡（差异 ¥{diff:,.2f}）"}
    return {"summary": "无余额数据"}
