"""I3 商誉 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/i3/ai-generate

sections: adj-note / adj-conclusion / impairment-analysis /
          dcf-parameter-suggestion / cgu-allocation-review /
          review-process-summary / disclosure-narrative
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

router = APIRouter(tags=["i3-ai"])


class I3AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class I3AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "adj-note",
    "adj-conclusion",
    "impairment-analysis",
    "dcf-parameter-suggestion",
    "cgu-allocation-review",
    "review-process-summary",
    "disclosure-narrative",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 I3《商誉》。
科目1711商誉（借方/资产类）。

商誉核心特殊规则：
1. 商誉不摊销！仅每年度末进行减值测试
2. 期末=期初+新并购(通常0)-减值（只减不增）
3. 商誉减值不可转回！
4. 商誉不能单独产生现金流→必须按资产组(CGU)进行减值测试
5. 减值分摊规则：先冲商誉（至零为止），剩余按比例分摊至资产组其他资产
6. 可收回金额=MAX(公允价值-处置费用, 使用价值DCF)
7. DCF模型：PV=Σ(FCF_i/(1+WACC)^i) + TV/(1+WACC)^n
8. 终值=FCF_n×(1+g)/(WACC-g)（永续增长模型/Gordon模型）

适用准则：CAS8资产减值、CAS20企业合并、CAS33合并财务报表。
WACC合理区间通常8%-15%，永续增长率通常0%-3%。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "adj-note": (
        "请生成I3商誉审定表的审计说明，分析科目1711商誉的变动情况。"
        "需涵盖：期初到期末的变动原因（有无新并购/有无减值）、"
        "商誉不摊销的确认、减值测试是否已执行、未审数与审定数的差异说明。"
        "重点关注：本期增加是否仅来自新并购，本期减少是否仅来自减值。"
    ),
    "adj-conclusion": (
        "请生成I3商誉审定表的审计结论，评价商誉科目的："
        "1) 存在性（商誉对应的子公司是否仍存在）\n"
        "2) 计价准确性（减值测试是否充分）\n"
        "3) 完整性（所有应确认减值是否已确认）\n"
        "说明审定数与试算平衡表是否一致、是否存在需调整事项。"
    ),
    "impairment-analysis": (
        "请生成商誉减值测试分析说明，评价以下方面：\n"
        "1) 减值迹象识别是否充分（被投资单位经营/行业/市场变化等）\n"
        "2) CGU划分是否合理（与内部报告管理层监控的最低层次一致）\n"
        "3) 减值分摊是否正确执行两步法（先冲商誉再按比例分摊）\n"
        "4) 减值金额=MAX(资产组账面-可收回金额, 0)计算是否准确\n"
        "5) 商誉减值是否存在转回情形（不得转回！）\n"
        "6) 本期减值是否充分反映资产组价值变动"
    ),
    "dcf-parameter-suggestion": (
        "请根据项目行业和宏观环境，建议DCF模型关键参数：\n"
        "1) WACC折现率建议区间及选取依据（资本资产定价模型CAPM各因子）\n"
        "2) 永续增长率建议区间（通常不超GDP增速）\n"
        "3) 收入增长率预测的合理性考量（行业增速、历史趋势、管理层预期）\n"
        "4) 预测期限建议（通常5年）\n"
        "5) 敏感性分析重点参数\n"
        "6) 常见审计关注点：折现率是否与风险匹配、增长率是否过于乐观"
    ),
    "cgu-allocation-review": (
        "请生成CGU资产组划分及商誉分摊合理性的复核意见：\n"
        "1) CGU划分是否与管理层监控商誉的最低层次一致\n"
        "2) CGU划分是否与上年一致，变更是否有合理原因\n"
        "3) 商誉在各CGU间的分摊比例是否合理\n"
        "4) CGU包含的其他资产范围是否完整\n"
        "5) CGU之间是否存在重大协同效应影响划分"
    ),
    "review-process-summary": (
        "请生成复核公司减值测试过程的总结评价：\n"
        "1) 管理层使用的估值模型是否适当\n"
        "2) 关键假设（折现率/增长率/预测期收入）是否合理\n"
        "3) 现金流预测是否与批准的预算/计划一致\n"
        "4) 折现率是否反映当前市场评估的货币时间价值及该资产特定风险\n"
        "5) 模型计算是否正确（数学验证）\n"
        "6) 上年假设与实际结果的比较（后视偏差检验）\n"
        "7) 整体评价：管理层减值测试结论是否可接受"
    ),
    "disclosure-narrative": (
        "请生成商誉附注披露的文字描述部分，包括：\n"
        "1) 商誉确认和计量的会计政策说明\n"
        "2) 商誉不摊销、每年减值测试的政策说明\n"
        "3) 减值测试方法（使用价值/公允价值减处置费用）\n"
        "4) 关键假设（折现率、预测期增长率、终值假设）\n"
        "5) 各CGU商誉金额、本期减值情况明细\n"
        "6) 敏感性分析：关键假设变动对可收回金额的影响"
    ),
}


@router.post("/api/workpapers/{wp_id}/i3/ai-generate")
async def i3_ai_generate(
    wp_id: str,
    body: I3AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> I3AiGenerateResponse:
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
        return I3AiGenerateResponse(content="", sources=[])
    return I3AiGenerateResponse(content=result, sources=[])


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
        logger.warning("I3 AI: project context 加载失败: %s", e)
    return ctx
