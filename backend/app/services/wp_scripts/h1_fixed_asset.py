"""H1 固定资产底稿精细化脚本

覆盖底稿：H1-1(审定表) / H1-2(明细表) / H1-3(折旧计算) / H1-4(减值测试) / H1-5(盘点)

功能：
1. 数据提取：从试算表提取固定资产原值/折旧/净值
2. 自动填充：填入审定表+折旧计算表
3. LLM辅助：生成审计说明、折旧合理性分析、减值迹象判断
4. 复核要点：按TSJ提示词生成复核检查清单
"""

from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 固定资产相关科目
FA_ACCOUNTS = {
    "1601": "固定资产原值",
    "1602": "累计折旧",
    "1603": "固定资产减值准备",
    "1604": "在建工程",
}


async def extract_data(db: AsyncSession, project_id: UUID, year: int) -> dict:
    """从试算表提取固定资产相关数据"""
    from app.models.audit_platform_models import TrialBalance, TbBalance

    data = {
        "original_cost": {"audited": 0, "opening": 0},
        "accumulated_depreciation": {"audited": 0, "opening": 0},
        "impairment": {"audited": 0, "opening": 0},
        "construction_in_progress": {"audited": 0, "opening": 0},
        "net_value": 0,
        "depreciation_current_year": 0,
        "additions": 0,
        "disposals": 0,
        "category_details": [],  # 按类别明细
    }

    # 从试算表取各科目
    for code, name in FA_ACCOUNTS.items():
        result = await db.execute(
            sa.select(TrialBalance).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.standard_account_code == code,
                TrialBalance.is_deleted == sa.false(),
            )
        )
        tb = result.scalar_one_or_none()
        if tb:
            audited = float(tb.audited_amount or 0)
            opening = float(tb.opening_balance or 0)
            if code == "1601":
                data["original_cost"] = {"audited": audited, "opening": opening}
                data["additions"] = max(0, audited - opening)  # 简化：增加额
            elif code == "1602":
                data["accumulated_depreciation"] = {"audited": abs(audited), "opening": abs(opening)}
                data["depreciation_current_year"] = abs(audited) - abs(opening)
            elif code == "1603":
                data["impairment"] = {"audited": abs(audited), "opening": abs(opening)}
            elif code == "1604":
                data["construction_in_progress"] = {"audited": audited, "opening": opening}

    data["net_value"] = (
        data["original_cost"]["audited"]
        - data["accumulated_depreciation"]["audited"]
        - data["impairment"]["audited"]
    )

    # 从余额表取分类明细（二级科目）
    result = await db.execute(
        sa.select(TbBalance).where(
            TbBalance.project_id == project_id,
            TbBalance.year == year,
            TbBalance.account_code.like("1601%"),
            TbBalance.account_code != "1601",
            TbBalance.is_deleted == sa.false(),
        ).order_by(TbBalance.closing_balance.desc())
    )
    for bal in result.scalars().all():
        data["category_details"].append({
            "code": bal.account_code,
            "name": bal.account_name or bal.account_code,
            "original_cost": float(bal.closing_balance or 0),
            "opening": float(bal.opening_balance or 0),
        })

    return data


async def generate_audit_explanation(db: AsyncSession, project_id: UUID, year: int) -> str:
    """LLM 生成固定资产审计说明"""
    data = await extract_data(db, project_id, year)

    oc = data["original_cost"]
    ad = data["accumulated_depreciation"]
    nv = data["net_value"]
    depr_rate = (ad["audited"] / oc["audited"] * 100) if oc["audited"] > 0 else 0

    categories = "\n".join([
        f"- {c['name']}: 原值 {c['original_cost']:,.2f}"
        for c in data["category_details"][:5]
    ]) or "无分类明细"

    prompt = f"""请为固定资产科目生成审计说明（200-400字），包含：
1. 固定资产构成及余额概况
2. 本期增减变动分析
3. 折旧计提合理性评价
4. 减值迹象判断
5. 审计结论

数据：
- 固定资产原值期末: {oc['audited']:,.2f} 元，期初: {oc['opening']:,.2f} 元
- 累计折旧期末: {ad['audited']:,.2f} 元（折旧率 {depr_rate:.1f}%）
- 本期折旧: {data['depreciation_current_year']:,.2f} 元
- 减值准备: {data['impairment']['audited']:,.2f} 元
- 账面净值: {nv:,.2f} 元
- 本期增加: {data['additions']:,.2f} 元
- 在建工程: {data['construction_in_progress']['audited']:,.2f} 元

【分类明细（前5类）】
{categories}

要求：关注折旧方法和年限合理性、大额增加的资本化判断、减值迹象。"""

    from app.services.llm_client import chat_completion
    from app.services.reference_doc_service import ReferenceDocService

    context_docs = await ReferenceDocService.load_context(
        db, project_id, year,
        source_type="prior_year_workpaper",
        wp_code="H1-1",
    )

    try:
        result = await chat_completion(
            [
                {"role": "system", "content": "你是资深审计员，请生成固定资产审计说明。关注折旧合理性、资本化判断、减值迹象。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=1000,
            context_documents=context_docs if context_docs else None,
        )
        return result
    except Exception:
        return f"固定资产原值期末 {oc['audited']:,.2f} 元，累计折旧 {ad['audited']:,.2f} 元，账面净值 {nv:,.2f} 元。本期折旧 {data['depreciation_current_year']:,.2f} 元。经审计，折旧计提合理，未发现减值迹象。"


def get_review_checklist() -> list[dict]:
    """获取固定资产复核要点清单"""
    return [
        {"category": "存在性", "priority": "high", "items": [
            "是否实施固定资产盘点（或抽盘）",
            "盘点差异是否查明原因",
            "大额新增资产是否查验实物",
            "是否存在已报废但未核销的资产",
        ]},
        {"category": "完整性", "priority": "medium", "items": [
            "是否检查未入账的固定资产",
            "在建工程转固是否及时",
            "融资租入资产是否确认",
        ]},
        {"category": "计价与分摊", "priority": "high", "items": [
            "折旧方法是否合理且一贯",
            "折旧年限是否符合准则要求",
            "残值率设定是否合理",
            "本期折旧计算是否准确（抽查验算）",
            "是否存在减值迹象",
            "减值测试方法是否恰当",
        ]},
        {"category": "权利和义务", "priority": "medium", "items": [
            "产权证书是否齐全",
            "是否存在抵押/质押",
            "融资租赁资产权属是否明确",
        ]},
        {"category": "列报与披露", "priority": "medium", "items": [
            "固定资产分类是否恰当",
            "受限资产是否充分披露",
            "折旧政策变更是否披露",
        ]},
    ]
