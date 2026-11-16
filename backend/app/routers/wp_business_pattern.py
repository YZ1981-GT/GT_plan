"""D2 业务模式分析 API

POST /api/projects/{project_id}/workpapers/D2/business-pattern-analysis

基于序时账客户付款数据分析客户付款周期分布，
返回 LLM 分类建议（当前为 stub 实现，真实 LLM 集成后续接入）。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers/D2",
    tags=["wp-business-pattern"],
)


class DateRange(BaseModel):
    """可选日期范围"""
    start_date: str | None = None
    end_date: str | None = None


class BusinessPatternRequest(BaseModel):
    """业务模式分析请求体"""
    date_range: DateRange | None = None


class CustomerPattern(BaseModel):
    """单个客户的付款模式"""
    customer: str
    payment_cycle_days: int
    category: str


class BusinessPatternResponse(BaseModel):
    """业务模式分析响应"""
    patterns: list[CustomerPattern]
    llm_suggestion: str


@router.post("/business-pattern-analysis", response_model=BusinessPatternResponse)
async def business_pattern_analysis(
    project_id: UUID,
    body: BusinessPatternRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("readonly")),
):
    """D2 业务模式分析

    基于序时账客户付款数据，分析客户付款周期分布，
    返回客户付款模式列表 + LLM 分类建议。

    输入：项目 ID + (可选) 日期范围
    输出：{ patterns: [{customer, payment_cycle_days, category}], llm_suggestion: str }
    """
    import sqlalchemy as sa
    from app.models.core import Project

    # 验证项目存在
    project = (await db.execute(
        sa.select(Project).where(Project.id == project_id)
    )).scalar_one_or_none()
    if not project:
        raise HTTPException(404, "项目不存在")

    if project.audit_year is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "AUDIT_YEAR_REQUIRED",
                "message": "项目未设置审计年度，无法分析业务模式",
            },
        )

    patterns = await _analyze_payment_patterns(
        db, project_id, body, year=project.audit_year
    )

    # LLM 建议（stub）
    llm_suggestion = _generate_stub_suggestion(patterns)

    return BusinessPatternResponse(
        patterns=patterns,
        llm_suggestion=llm_suggestion,
    )


async def _analyze_payment_patterns(
    db: AsyncSession,
    project_id: UUID,
    body: BusinessPatternRequest | None,
    *,
    year: int,
) -> list[CustomerPattern]:
    """按项目年度的辅助明细账分析客户付款模式。

    客户名称来自 ``tb_aux_balance`` 的辅助余额维度，交易笔数和金额来自
    ``tb_aux_ledger`` 的辅助明细。两张表按项目、年度、科目、辅助类型和辅助
    编码关联，不能把辅助字段当成 ``tb_ledger`` 的列读取。
    """
    import logging
    from datetime import date

    import sqlalchemy as sa

    from app.models.audit_platform_models import TbAuxBalance, TbAuxLedger
    from app.services.dataset_query import get_active_filter

    try:
        balance_filter = await get_active_filter(
            db,
            TbAuxBalance.__table__,
            project_id,
            year,
            strict=True,
        )
        ledger_filter = await get_active_filter(
            db,
            TbAuxLedger.__table__,
            project_id,
            year,
            strict=True,
        )

        stmt = sa.select(
            TbAuxBalance.aux_name,
            TbAuxBalance.aux_code,
            sa.func.sum(TbAuxLedger.debit_amount).label("total_debit"),
            sa.func.count(TbAuxLedger.id).label("txn_count"),
        ).select_from(TbAuxLedger).join(
            TbAuxBalance,
            sa.and_(
                TbAuxBalance.project_id == TbAuxLedger.project_id,
                TbAuxBalance.year == TbAuxLedger.year,
                TbAuxBalance.account_code == TbAuxLedger.account_code,
                TbAuxBalance.aux_type == TbAuxLedger.aux_type,
                TbAuxBalance.aux_code == TbAuxLedger.aux_code,
                TbAuxBalance.is_deleted == sa.false(),
            ),
        ).where(
            ledger_filter,
            balance_filter,
            TbAuxLedger.account_code.like("1122%"),
            TbAuxBalance.aux_type == "客户",
            TbAuxBalance.aux_code.isnot(None),
            TbAuxBalance.aux_name.isnot(None),
            TbAuxBalance.aux_name != "",
        ).group_by(
            TbAuxBalance.account_code,
            TbAuxBalance.aux_type,
            TbAuxBalance.aux_code,
            TbAuxBalance.aux_name,
        ).order_by(sa.desc("total_debit")).limit(10)

        date_range = body.date_range if body else None
        if date_range:
            try:
                start_date = (
                    date.fromisoformat(date_range.start_date)
                    if date_range.start_date
                    else None
                )
                end_date = (
                    date.fromisoformat(date_range.end_date)
                    if date_range.end_date
                    else None
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "INVALID_DATE_RANGE",
                        "message": "日期范围格式必须为 YYYY-MM-DD",
                    },
                ) from exc
            if start_date and end_date and start_date > end_date:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "INVALID_DATE_RANGE",
                        "message": "开始日期不能晚于结束日期",
                    },
                )
            if start_date:
                stmt = stmt.where(TbAuxLedger.voucher_date >= start_date)
            if end_date:
                stmt = stmt.where(TbAuxLedger.voucher_date <= end_date)

        rows = (await db.execute(stmt)).all()
        patterns: list[CustomerPattern] = []
        for row in rows:
            cycle_days = max(30, min(365, int(row.txn_count * 15)))
            patterns.append(
                CustomerPattern(
                    customer=str(row.aux_name),
                    payment_cycle_days=cycle_days,
                    category=_classify_payment_cycle(cycle_days),
                )
            )
        return patterns
    except HTTPException:
        raise
    except Exception as exc:
        logging.getLogger(__name__).exception(
            "分析客户付款模式失败 [project=%s year=%s]", project_id, year
        )
        raise HTTPException(
            status_code=503,
            detail={
                "code": "BUSINESS_PATTERN_QUERY_FAILED",
                "message": "业务模式分析数据查询失败，请稍后重试",
            },
        ) from exc


def _classify_payment_cycle(days: int) -> str:
    """按付款周期天数分类"""
    if days <= 15:
        return "现销型"
    elif days <= 45:
        return "短期信用"
    elif days <= 90:
        return "中期信用"
    else:
        return "长期信用"


def _generate_stub_suggestion(patterns: list[CustomerPattern]) -> str:
    """生成 LLM 建议（stub 实现）

    真实实现将调用 wp_ai_service 生成基于客户付款模式的业务分析建议。
    """
    if not patterns:
        return "暂无足够数据进行业务模式分析，请确保已导入序时账数据。"

    categories = {}
    for p in patterns:
        categories[p.category] = categories.get(p.category, 0) + 1

    parts = []
    parts.append(f"基于 {len(patterns)} 个主要客户的付款数据分析：")

    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        parts.append(f"- {cat}客户 {count} 个")

    # 风险提示
    long_term = [p for p in patterns if p.payment_cycle_days > 90]
    if long_term:
        parts.append(
            f"\n⚠ 风险提示：{len(long_term)} 个客户付款周期超过 90 天，"
            "建议关注应收账款回收风险及坏账准备计提充分性。"
        )

    parts.append(
        "\n建议：根据客户付款模式分类，对长期信用客户加强账龄分析和函证程序。"
    )

    return "\n".join(parts)
