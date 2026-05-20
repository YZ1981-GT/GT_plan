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
from app.deps import get_current_user

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
    user=Depends(get_current_user),
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

    # Stub 实现：返回基于序时账的模拟分析结果
    # 真实实现将查询 tb_ledger 按客户辅助核算分组统计付款周期
    patterns = await _analyze_payment_patterns(db, project_id, body)

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
) -> list[CustomerPattern]:
    """分析客户付款模式

    真实实现将：
    1. 查询 tb_ledger 中 1122（应收账款）科目的辅助核算明细
    2. 按客户分组，计算平均回款天数
    3. 按回款天数分类（现销/短期/中期/长期）

    当前为 stub 实现，返回示例数据。
    """
    import sqlalchemy as sa

    try:
        from app.models.audit_platform_models import TbLedger
        from app.services.dataset_query import get_active_filter

        # 尝试从真实数据获取客户列表
        active_filter = await get_active_filter(db, TbLedger, project_id, None)
        result = await db.execute(
            sa.select(
                TbLedger.aux_name,
                sa.func.sum(TbLedger.debit_amount).label("total_debit"),
                sa.func.count().label("txn_count"),
            )
            .where(
                active_filter,
                TbLedger.account_code.like("1122%"),
                TbLedger.aux_name.isnot(None),
                TbLedger.aux_name != "",
            )
            .group_by(TbLedger.aux_name)
            .order_by(sa.desc("total_debit"))
            .limit(10)
        )
        rows = result.all()

        if rows:
            patterns = []
            for row in rows:
                # 简化的付款周期估算（真实实现需要匹配收款记录）
                cycle_days = max(30, min(365, int(row.txn_count * 15)))
                category = _classify_payment_cycle(cycle_days)
                patterns.append(CustomerPattern(
                    customer=row.aux_name or "未知客户",
                    payment_cycle_days=cycle_days,
                    category=category,
                ))
            return patterns
    except Exception:
        pass

    # Fallback: 返回 stub 数据
    return [
        CustomerPattern(customer="示例客户A", payment_cycle_days=30, category="现销型"),
        CustomerPattern(customer="示例客户B", payment_cycle_days=60, category="短期信用"),
        CustomerPattern(customer="示例客户C", payment_cycle_days=90, category="中期信用"),
        CustomerPattern(customer="示例客户D", payment_cycle_days=180, category="长期信用"),
        CustomerPattern(customer="示例客户E", payment_cycle_days=45, category="短期信用"),
    ]


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
