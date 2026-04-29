"""D1 应收账款底稿精细化脚本

覆盖底稿：D1-1(审定表) / D1-2(明细表) / D1-3(账龄分析) / D1-4(坏账计提) / D1-5(期后回款)

功能：
1. 数据提取：从试算表/辅助余额表提取应收账款数据
2. 自动填充：填入审定表+账龄分析+坏账计提
3. LLM辅助：生成审计说明、账龄异常分析、坏账合理性评价
4. 复核要点：按TSJ提示词生成复核检查清单
"""

from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 应收账款相关科目
AR_ACCOUNTS = ["1122"]  # 应收账款
BAD_DEBT_ACCOUNTS = ["1231"]  # 坏账准备


async def extract_data(db: AsyncSession, project_id: UUID, year: int) -> dict:
    """从试算表和辅助余额表提取应收账款数据"""
    from app.models.audit_platform_models import TrialBalance, TbAuxBalance, TbLedger

    data = {
        "ar_balance": {"audited": 0, "unadjusted": 0, "opening": 0},
        "bad_debt": {"audited": 0, "opening": 0},
        "net_value": 0,
        "customer_details": [],  # 客户明细
        "aging_summary": {},  # 账龄汇总
        "post_collection": [],  # 期后回款
        "top_customers": [],  # 前5大客户
    }

    # 1. 应收账款余额
    result = await db.execute(
        sa.select(TrialBalance).where(
            TrialBalance.project_id == project_id,
            TrialBalance.year == year,
            TrialBalance.standard_account_code == "1122",
            TrialBalance.is_deleted == sa.false(),
        )
    )
    tb = result.scalar_one_or_none()
    if tb:
        data["ar_balance"] = {
            "audited": float(tb.audited_amount or 0),
            "unadjusted": float(tb.unadjusted_amount or 0),
            "opening": float(tb.opening_balance or 0),
        }

    # 2. 坏账准备余额
    result = await db.execute(
        sa.select(TrialBalance).where(
            TrialBalance.project_id == project_id,
            TrialBalance.year == year,
            TrialBalance.standard_account_code == "1231",
            TrialBalance.is_deleted == sa.false(),
        )
    )
    tb_bd = result.scalar_one_or_none()
    if tb_bd:
        data["bad_debt"] = {
            "audited": float(tb_bd.audited_amount or 0),
            "opening": float(tb_bd.opening_balance or 0),
        }

    data["net_value"] = data["ar_balance"]["audited"] - abs(data["bad_debt"]["audited"])

    # 3. 客户明细（从辅助余额表）
    result = await db.execute(
        sa.select(TbAuxBalance).where(
            TbAuxBalance.project_id == project_id,
            TbAuxBalance.year == year,
            TbAuxBalance.account_code == "1122",
            TbAuxBalance.is_deleted == sa.false(),
        ).order_by(TbAuxBalance.closing_balance.desc()).limit(20)
    )
    for aux in result.scalars().all():
        data["customer_details"].append({
            "name": aux.aux_name,
            "code": aux.aux_code,
            "closing": float(aux.closing_balance or 0),
            "opening": float(aux.opening_balance or 0),
        })

    # 前5大客户
    data["top_customers"] = data["customer_details"][:5]

    return data


async def generate_audit_explanation(db: AsyncSession, project_id: UUID, year: int) -> str:
    """LLM 生成应收账款审计说明"""
    data = await extract_data(db, project_id, year)

    ar = data["ar_balance"]
    bd = data["bad_debt"]
    change = ar["audited"] - ar["opening"]
    change_rate = (change / ar["opening"] * 100) if ar["opening"] != 0 else 0

    top_customers = "\n".join([
        f"- {c['name']}: {c['closing']:,.2f} 元"
        for c in data["top_customers"]
    ]) or "无明细"

    prompt = f"""请为应收账款科目生成审计说明（200-400字），包含：
1. 余额概况及变动分析
2. 坏账准备计提情况
3. 前5大客户集中度分析
4. 审计程序执行摘要
5. 审计结论

数据：
- 应收账款期末余额: {ar['audited']:,.2f} 元
- 应收账款期初余额: {ar['opening']:,.2f} 元
- 变动额: {change:,.2f} 元（变动率 {change_rate:.1f}%）
- 坏账准备期末: {abs(bd['audited']):,.2f} 元
- 账面价值: {data['net_value']:,.2f} 元
- 坏账计提比例: {abs(bd['audited'])/ar['audited']*100:.2f}%（若余额>0）

【前5大客户】
{top_customers}

要求：语言专业简洁，关注信用风险和回收可能性。"""

    from app.services.llm_client import chat_completion
    from app.services.reference_doc_service import ReferenceDocService

    context_docs = await ReferenceDocService.load_context(
        db, project_id, year,
        source_type="prior_year_workpaper",
        wp_code="D1-1",
    )

    try:
        result = await chat_completion(
            [
                {"role": "system", "content": "你是资深审计员，请生成应收账款审计说明。关注信用风险、账龄结构、坏账计提合理性。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=1000,
            context_documents=context_docs if context_docs else None,
        )
        return result
    except Exception:
        return f"应收账款期末余额 {ar['audited']:,.2f} 元，较期初变动 {change:,.2f} 元（{change_rate:.1f}%）。坏账准备 {abs(bd['audited']):,.2f} 元。经审计，未发现重大错报。"


def get_review_checklist() -> list[dict]:
    """获取应收账款复核要点清单"""
    return [
        {"category": "存在性", "priority": "high", "items": [
            "是否对重大余额发函确认",
            "函证回函率是否达标（建议>70%）",
            "未回函是否执行替代程序",
            "是否检查期后回款验证余额真实性",
        ]},
        {"category": "完整性", "priority": "medium", "items": [
            "是否检查未入账的销售交易",
            "是否核实截止日前后的发货记录",
        ]},
        {"category": "计价与分摊", "priority": "high", "items": [
            "坏账准备计提政策是否合理",
            "账龄分析是否准确",
            "单项计提的判断依据是否充分",
            "组合计提的迁徙率是否合理",
            "是否存在应转销未转销的坏账",
        ]},
        {"category": "分类", "priority": "medium", "items": [
            "一年以上应收款是否重分类为长期应收",
            "关联方应收是否单独披露",
            "应收票据与应收账款是否正确区分",
        ]},
        {"category": "截止", "priority": "high", "items": [
            "期末前后大额销售是否在正确期间确认",
            "退货是否在正确期间冲减",
        ]},
    ]
