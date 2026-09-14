"""I1 无形资产 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/i1/ai-generate

sections: adj-note / adj-conclusion / policy-analysis /
          amortization-reasonableness / impairment-analysis / disclosure-narrative
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

router = APIRouter(tags=["i1-ai"])


class I1AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class I1AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "adj-note",
    "adj-conclusion",
    "policy-analysis",
    "amortization-reasonableness",
    "impairment-analysis",
    "disclosure-narrative",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 I1《无形资产、累计摊销及减值准备》。
科目1701无形资产（借方/资产类）+ 1702累计摊销（贷方/资产备抵类）+ 1703无形资产减值准备（贷方/资产备抵类）。
核心关注：资产类三角勾稽（期末=期初+增加-减少）、摊销方法（直线法/剩余年限法）、
使用寿命估计合理性、减值DCF测试（可收回金额=MAX(公允-处置费, 使用价值现值)）、
权属检查逐项核验、I2开发支出资本化转入联动。
CAS6无形资产准则：确认条件（经济利益+成本可靠计量）、使用寿命有限/不确定分类、
摊销（直线法为主，剩余年限法含减值重算基数）、减值（CAS8）。
净值=原值-累计摊销-减值准备。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "adj-note": (
        "请生成I1无形资产审定表的审计说明，分析三科目（原值/累计摊销/减值准备）各分类的"
        "三角勾稽结果、期初到期末变动的主要原因、未审数与审定数的差异说明。"
        "需涵盖：新增无形资产的取得方式、处置/报废项目、摊销计提是否充分、"
        "是否存在减值迹象等关键事项。"
    ),
    "adj-conclusion": (
        "请生成I1无形资产审定表的审计结论，评价无形资产科目整体的真实性（存在性）、"
        "完整性和计价准确性，说明三角勾稽是否通过、是否发现需要调整的重大事项、"
        "审定数与试算平衡表是否一致。结论应覆盖1701/1702/1703三个科目。"
    ),
    "policy-analysis": (
        "请生成I1-4摊销减值政策检查的分析评价，逐项评价被审计单位：\n"
        "1) 无形资产确认条件是否符合CAS6\n"
        "2) 使用寿命有限/不确定分类是否恰当\n"
        "3) 摊销方法（直线法）和摊销起点是否合理\n"
        "4) 残值率设定是否恰当（通常为零）\n"
        "5) 减值迹象判断标准是否完整（CAS8）\n"
        "6) 减值测试频率是否符合准则要求（使用寿命不确定的须每年测试）\n"
        "7) 会计政策与上期是否一致"
    ),
    "amortization-reasonableness": (
        "请生成摊销合理性分析说明，评价以下方面：\n"
        "1) 各项无形资产摊销方法选用的合理性（直线法为主）\n"
        "2) 使用寿命估计的依据和合理性（合同期/法定期/预期使用期取较短）\n"
        "3) 摊销金额测算与账面记录的差异及原因\n"
        "4) 本期新增/处置资产的摊销起止月份是否正确\n"
        "5) 含减值情况下摊销基数重算是否正确（原值-残值-累计摊销-减值准备）÷剩余月数\n"
        "6) 摊销费用在各部门（管理/销售/研发/制造）的分配是否合理"
    ),
    "impairment-analysis": (
        "请生成减值测试分析说明，评价以下方面：\n"
        "1) 减值迹象判断是否充分（技术过时/市场变化/经济绩效下降等）\n"
        "2) 可收回金额确定方法（公允价值-处置费用 vs 使用价值DCF）\n"
        "3) DCF关键假设的合理性：折现率选取、预测期现金流预期、永续增长率\n"
        "4) 应计提减值=MAX(账面净值-可收回金额, 0)的计算是否准确\n"
        "5) 已计提与应计提的差额分析\n"
        "6) 使用寿命不确定的无形资产是否按准则每年进行减值测试\n"
        "7) 减值损失一经确认不得转回（CAS8规定）的执行情况"
    ),
    "disclosure-narrative": (
        "请生成无形资产附注披露的文字描述部分，包括：\n"
        "1) 无形资产的确认和计量政策说明\n"
        "2) 使用寿命有限的无形资产摊销方法及年限\n"
        "3) 使用寿命不确定的无形资产判断依据\n"
        "4) 内部研究开发支出资本化的标准说明\n"
        "5) 减值测试方法及关键假设\n"
        "6) 本期重大变动事项说明（新增/处置/减值计提等）"
    ),
}


@router.post("/api/workpapers/{wp_id}/i1/ai-generate")
async def i1_ai_generate(
    wp_id: str,
    body: I1AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> I1AiGenerateResponse:
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
        return I1AiGenerateResponse(content="", sources=[])
    return I1AiGenerateResponse(content=result, sources=[])


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
        logger.warning("I1 AI: project context 加载失败: %s", e)
    return ctx
