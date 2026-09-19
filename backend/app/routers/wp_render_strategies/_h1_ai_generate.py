"""H1 固定资产 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/h1/ai-generate

sections: adj-note / adj-conclusion / policy-evaluation / analysis-change /
          depreciation-summary / impairment-conclusion / stocktake-summary /
          stocktake-plan / disposal-note / idle-note / idle-conclusion
"""

from __future__ import annotations

import logging
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.llm_client import chat_completion

logger = logging.getLogger(__name__)

router = APIRouter(tags=["h1-ai"])


class H1AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class H1AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "adj-note",
    "adj-conclusion",
    "policy-evaluation",
    "analysis-change",
    "depreciation-summary",
    "depreciation-alloc-note",
    "impairment-conclusion",
    "stocktake-summary",
    "stocktake-plan",
    "disposal-note",
    "idle-note",
    "idle-conclusion",
    "title-building-note",
    "title-vehicle-note",
    "related-party-note",
    "operating-lease-note",
    "finance-lease-note",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 H1《固定资产》。
科目1601固定资产（借方/资产类）+ 1602累计折旧（贷方/资产备抵类）。
核心关注：资产类三角勾稽（期末=期初+增加-减少）、折旧四种方法计算验证、
减值DCF资产组测试、实物监盘三阶段流程、权属检查逐项核验。
CAS4固定资产准则：确认条件（经济利益+成本可靠）、折旧（直线/双倍余额/年数总和/工作量）、
减值（CAS8资产减值-可收回金额=MAX(公允-处置费,使用价值现值)）。
闲置固定资产（未使用/不需用）：通常应继续计提折旧；闲置属CAS8第5条减值迹象之一。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "adj-note": (
        "请生成H1-1固定资产审定表的审计说明，分析原值/累计折旧/减值准备各分类的三角勾稽结果、"
        "期初到期末变动的主要原因（尤其净值变动率≥30%的类别）、未审数与审定数的差异说明，"
        "以及与H1-2明细、试算平衡表的勾稽情况。"
    ),
    "adj-conclusion": (
        "请生成H1-1固定资产审定表的审计结论，评价固定资产原值、累计折旧及减值准备整体的"
        "真实性、完整性和计价准确性，说明是否发现需要调整的重大事项。"
    ),
    "policy-evaluation": (
        "请生成H1-5会计政策估计检查的审计师评价，逐项评价被审计单位固定资产确认条件、"
        "分类与使用年限、折旧方法与残值率、后续支出资本化/费用化标准、减值政策的恰当性。"
    ),
    "analysis-change": (
        "请生成H1-6固定资产分析表的审计说明，须覆盖："
        "（1）比例分析：净值/资产总额、本期折旧/原值、累计折旧/原值、减值/原值、原值/产量、"
        "租入占比、租金收入/原值、维修费用/原值等指标本期与上期比较及异常变动解释；"
        "（2）结构分析：各类资产净值占比、成新率偏低类别原因；"
        "（3）变动分析：各类增加率/减少率/净变动率异常项及是否已追查至H1-7/H1-8；"
        "（4）总体评价：分析性程序是否识别需追加细节测试的领域。"
    ),
    "depreciation-summary": (
        "请生成H1-12折旧测算表的审计汇总说明，说明测算折旧与账面折旧的总差异、"
        "差异较大的资产类别及原因、折旧方法和参数的合理性评价。"
    ),
    "impairment-conclusion": (
        "请生成H1-14减值测算表的审计结论，评价：（1）CAS8第5条六项减值迹象判断是否充分；"
        "（2）测试单元（单项资产/资产组）划分是否合理；（3）可收回金额=MAX(公允净额,DCF)及关键假设；"
        "（4）应计提与已计提差异及调整建议；（5）是否存在将固定资产减值准备转回损益的不当情形（CAS8第17条不得转回）。"
    ),
    "stocktake-summary": (
        "请生成H1-11监盘小结的总体结论，按下列要点组织（直接输出正文）："
        "（1）监盘日期、检查项数、账实相符率；（2）盘盈/盘亏数量与金额及性质；"
        "（3）与H1-9计划样本量对照结论；（4）复盘覆盖率与正确率；"
        "（5）异常事项及跟进；（6）对固定资产存在性认定的总体意见。"
        "若 relatedContext 含 ruleDraft，可在其基础上润色，勿编造未提供的金额。"
    ),
    "stocktake-plan": (
        "请生成H1-9固定资产监盘计划结论（直接输出正文，2~8句）："
        "概括存在性风险应对、拟监盘时间与地点、方法（全面/抽样）、类别覆盖率、"
        "双向抽查（账面→实物/实物→账面）安排、预计复盘比例、对企业盘点计划评价、"
        "推算方法及专业胜任能力结论，明确是否可进入H1-10执行。"
        "若 relatedContext 含 ruleDraft，可在其基础上润色，勿编造未提供的金额与比例。"
    ),
    "disposal-note": (
        "请生成H1-8固定资产减少检查的审计说明，须覆盖："
        "（1）抽样方法、本期减少合计来源（H1-1/H1-2）及检查比例是否充分；"
        "（2）处置/报废审批合规性与关键证据（申报单、合同、发票）；"
        "（3）净值与清理净损益勾稽（净值=原值-累计折旧-减值；净损益=收入-净值-费用）；"
        "（4）关联方出售是否取得评估定价；报废无清理收入时是否核实残值回收/保险赔款；"
        "（5）与 H6 固定资产清理、H10 资产处置损益的联动一致性。"
    ),
    "idle-note": (
        "请生成H1-4闲置固定资产检查表的审计说明（直接输出正文），须覆盖："
        "（1）闲置/未使用/不需用识别范围与来源（H1-2/监盘）；"
        "（2）观察状况与是否按规定继续计提折旧（CAS4），对停提异常的核实结论；"
        "（3）CAS8减值迹象判断及与H1-14联动；"
        "（4）主要项目摘要。"
        "若 relatedContext 含 noteDraft/ruleDraft，可在其基础上润色，勿编造未提供的金额与项数。"
    ),
    "idle-conclusion": (
        "请生成H1-4闲置固定资产检查表的审计结论（直接输出正文，3~8句）："
        "概括闲置资产规模（未使用/不需用）、折旧处理合规性、减值迹象与计提充分性、"
        "需跟进事项（如停提或未计提减值），并给出是否在所有重大方面符合企业会计准则的总体意见。"
        "若 relatedContext 含 ruleDraft，可在其基础上润色，勿编造未提供的金额与项数。"
    ),
    "depreciation-alloc-note": (
        "请生成H1-13折旧分配分析表的审计说明，须覆盖："
        "（1）各类别折旧分配至生产成本/制造费用/销售费用/管理费用/研发费用的依据（用途/部门）；"
        "（2）横向勾稽：本表各行分配合计与H1-12折旧测算合计的差异说明；"
        "（3）纵向勾稽：各费用列合计与对方底稿（F5/F2/K8/K9/I6）的差异原因；"
        "（4）总体结论：折旧分配是否恰当反映固定资产用途及计入恰当费用科目。"
    ),
    "title-building-note": (
        "请生成H1-16房屋建筑物权属检查表的审计说明，须覆盖："
        "（1）检查范围与方法（全查/抽样）；"
        "（2）权利人是否为被审计单位，非本单位权证数量及代持/控制依据；"
        "（3）抵押/查封等受限情况及是否已纳入附注受限资产披露；"
        "（4）未办证在建转固情况及对权属认定的影响；"
        "（5）权证核对结论汇总（相符/不符/未取得权证）。"
    ),
    "title-vehicle-note": (
        "请生成H1-17运输设备权属检查表的审计说明，须覆盖："
        "（1）检查范围与方法；"
        "（2）登记证书/行驶证所有人是否为被审计单位；"
        "（3）年检有效性（截止日与资产负债表日对比，过期车辆及影响）；"
        "（4）登记栏抵押/查封限制及附注披露；"
        "（5）核对结论汇总及异常事项。"
    ),
    "related-party-note": (
        "请生成H1-18关联交易检查表的审计说明，须覆盖："
        "（1）合并范围外关联方识别与确认范围；"
        "（2）购入/出售/无偿调拨的定价政策与公允性判断（评估价差异率）；"
        "（3）入账差异分析（购入时入账价值与购买价款差额原因）；"
        "（4）出售损益与H10处置损益勾稽结果；"
        "（5）与A7-1关联方披露的交叉核对结论。"
    ),
    "operating-lease-note": (
        "请生成H1-19经营租出固定资产检查表的审计说明，须覆盖："
        "（1）经营租出资产清单核对（资产名称/承租方/合同）；"
        "（2）折旧费用核对：本期应计折旧与账面其他业务支出差异原因；"
        "（3）租金收入核对：本期应计租金与账面其他业务收入差异原因；"
        "（4）收益率分析：与市场租金偏离超20%的项目及原因；"
        "（5）关联方租赁的公允性判断。"
    ),
    "finance-lease-note": (
        "请生成H1-20融资租出固定资产检查表的审计说明，须覆盖："
        "（1）CAS21融资租赁五项判断依据及分类结论；"
        "（2）初始计量（最低租赁收款额/未担保余值/初始直接费用/应收融资租赁款/未确认融资收益）；"
        "（3）内含利率与收益分配分摊表的合理性；"
        "（4）与G5长期应收款科目的勾稽（净投资/未确认收益）；"
        "（5）期末重要假设（余值/利率）变更的影响评估。"
    ),
}


@router.post("/api/workpapers/{wp_id}/h1/ai-generate")
async def h1_ai_generate(
    wp_id: str,
    body: H1AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> H1AiGenerateResponse:
    if not getattr(settings, "WP_AI_SERVICE_ENABLED", True):
        raise HTTPException(503, "AI 服务未启用")
    if body.section not in _SUPPORTED_SECTIONS:
        raise HTTPException(400, f"不支持的 section: {body.section}。支持: {sorted(_SUPPORTED_SECTIONS)}")

    project_context = await _load_project_context(wp_id, db)
    user_prompt = _build_user_prompt(body.section, body.existingContent, body.relatedContext, project_context)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    result = await chat_completion(messages=messages, temperature=0.3, max_tokens=2000)
    if isinstance(result, str) and result.startswith("["):
        return H1AiGenerateResponse(content="", sources=[])
    return H1AiGenerateResponse(content=result, sources=[])


def _build_user_prompt(
    section: str,
    existing_content: str,
    related_context: dict[str, Any],
    project_context: dict,
) -> str:
    parts: list[str] = [f"## 任务\n{_SECTION_PROMPTS.get(section, '请生成审计文本。')}\n"]
    ctx_lines = []
    if project_context.get("client_name"):
        ctx_lines.append(f"客户名称：{project_context['client_name']}")
    if project_context.get("audit_year"):
        ctx_lines.append(f"审计年度：{project_context['audit_year']}年")
    if project_context.get("business_category"):
        ctx_lines.append(f"行业：{project_context['business_category']}")
    if ctx_lines:
        parts.append("## 项目信息\n" + "\n".join(ctx_lines) + "\n")
    if related_context:
        ctx_str = "\n".join(f"- {k}: {v}" for k, v in related_context.items() if v)
        if ctx_str:
            parts.append(f"## 底稿数据\n{ctx_str}\n")
    if existing_content:
        parts.append(f"## 已有内容\n{existing_content[:2000]}\n请补充完善。")
    else:
        parts.append("请根据以上信息生成专业初稿。")
    return "\n".join(parts)


async def _load_project_context(wp_id: str, db: AsyncSession) -> dict:
    ctx: dict = {"client_name": "", "audit_year": "", "business_category": ""}
    try:
        result = await db.execute(
            sa.text("""
                SELECT p.client_name, p.audit_year, p.business_category
                FROM working_paper wp
                JOIN projects p ON wp.project_id = p.id
                WHERE wp.id = :wp_id
            """),
            {"wp_id": wp_id},
        )
        row = result.fetchone()
        if row:
            ctx["client_name"] = row.client_name or ""
            ctx["audit_year"] = str(row.audit_year) if row.audit_year else ""
            ctx["business_category"] = row.business_category or ""
    except Exception as e:
        logger.warning("H1 AI: project context 加载失败: %s", e)
    return ctx
