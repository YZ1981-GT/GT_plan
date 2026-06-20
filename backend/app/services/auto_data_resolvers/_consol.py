"""合并范围 / 抵销 / 内部往来 / 合并试算 / 现金流 域 resolvers。"""
from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auto_data_resolvers import auto_resolver


@auto_resolver("consol_scope_status")
async def _resolve_consol_scope(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """合并范围纳入子公司数量统计。

    数据来源: consol_scope 表（is_included=true）
    返回结构: {"summary": str}
    """
    from app.models.consolidation_models import ConsolScope
    stmt = sa.select(sa.func.count()).select_from(ConsolScope).where(
        ConsolScope.project_id == project_id,
        ConsolScope.is_included == sa.true(),
        ConsolScope.is_deleted == sa.false(),
    )
    r = await db.execute(stmt)
    count = r.scalar() or 0
    return {"summary": f"已纳入{count}家子公司" if count else "待确定"}


@auto_resolver("consol_elimination_count")
async def _resolve_consol_elim(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """合并抵销分录数量统计。

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
    return {"summary": f"共{count}笔抵销分录" if count else "无"}


@auto_resolver("consol_internal_trade_status")
async def _resolve_consol_trade(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """内部往来交易笔数统计。

    数据来源: internal_trade 表
    返回结构: {"summary": str}
    """
    from app.models.consolidation_models import InternalTrade
    stmt = sa.select(sa.func.count()).select_from(InternalTrade).where(
        InternalTrade.project_id == project_id,
    )
    r = await db.execute(stmt)
    count = r.scalar() or 0
    return {"summary": f"内部往来{count}笔" if count else "无内部往来"}


@auto_resolver("consol_trial_balance_check")
async def _resolve_consol_tb(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """合并试算平衡验证（AJE/RJE 调整净额检查）。

    数据来源: trial_balance 表（aje_adjustment / rje_adjustment 列）
    返回结构: {"summary": str}（含 AJE/RJE 净差异金额）
    """
    from app.models.audit_platform_models import TrialBalance
    tb_t = TrialBalance.__table__
    stmt = sa.select(
        sa.func.coalesce(sa.func.sum(tb_t.c.aje_adjustment), 0).label("aje_sum"),
        sa.func.coalesce(sa.func.sum(tb_t.c.rje_adjustment), 0).label("rje_sum"),
    ).where(
        tb_t.c.project_id == project_id,
        tb_t.c.year == year,
        tb_t.c.is_deleted == sa.false(),
    )
    r = await db.execute(stmt)
    row = r.first()
    if row:
        aje = float(row.aje_sum)
        rje = float(row.rje_sum)
        if abs(aje) < 0.01 and abs(rje) < 0.01:
            return {"summary": "✓ 合并试算平衡"}
        return {"summary": f"⚠️ 调整净差异 AJE ¥{aje:,.0f} / RJE ¥{rje:,.0f}"}
    return {"summary": "无合并试算数据"}


# ═══════════════════════════════════════════════════════════════════════════════
# 现金流 / 复核签字 / 底稿完成率
# ═══════════════════════════════════════════════════════════════════════════════


@auto_resolver("cf_verification_status")
async def _resolve_cf(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """现金流量表勾稽验证状态（通过项 / 总项比率）。

    数据来源: cf_verification_result 表
    返回结构: {"summary": str, "link": {"type": str, "target": str}}
    """
    from app.models.cf_verification_models import CfVerificationResult
    stmt = sa.select(
        sa.func.count(),
        sa.func.count().filter(CfVerificationResult.pass_ == sa.true()),
    ).where(
        CfVerificationResult.project_id == project_id,
        CfVerificationResult.year == year,
    )
    result = await db.execute(stmt)
    total, passed = result.one()
    if total == 0:
        summary = "未执行"
    elif passed == total:
        summary = f"全部通过（{total}项）"
    else:
        summary = f"通过{passed}/{total}项"
    return {"summary": summary, "link": {"type": "cf_verification", "target": "cash_flow_verification"}}
