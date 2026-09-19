"""I4 长期待摊费用 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/i4/ai-generate

sections: amort-policy / targeted-check / adj-note / adj-conclusion / disclosure-narrative
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

router = APIRouter(tags=["i4-ai"])


class I4AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class I4AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "amort-policy",
    "targeted-check",
    "adj-note",
    "adj-conclusion",
    "disclosure-narrative",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 I4《长期待摊费用》。
科目1801长期待摊费用（借方/资产类）。

长期待摊费用核心规则：
1. 期末余额=期初+增加-摊销-减少（标准资产类三角勾稽）
2. 摊销方法：
   - 直线法（按月平均摊销）：月摊销=原始金额÷摊销总月数
   - 工作量法（按产量/使用量摊销）：月摊销=原始金额×(本月工作量÷总预计工作量)
3. 常见项目类型：装修费、开办费、租入固定资产改良、大修理支出
4. 摊销期限：根据受益期确定（通常合同期或预计受益期）
5. 审定数=未审数+AJE+RJE
6. 已全部摊销完毕的项目应及时转销

适用准则：CAS4固定资产（改良支出参照）、企业所得税法第十三条。
输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "amort-policy": (
        "请生成I4长期待摊费用的摊销政策检查意见，分析以下方面：\n"
        "1) 摊销方法选择是否适当（直线法/工作量法的适用场景）\n"
        "2) 摊销期限（受益期）估计是否合理\n"
        "3) 摊销起始时点是否正确（自达到预定可使用状态次月起）\n"
        "4) 摊销政策是否与上年一致，有无变更\n"
        "5) 变更处理是否符合会计估计变更的规定（未来适用法）\n"
        "6) 已摊完项目是否及时转销"
    ),
    "targeted-check": (
        "请生成I4长期待摊费用针对性检查意见，关注以下风险点：\n"
        "1) 大额新增项目：是否有合同/发票支持、金额是否合理\n"
        "2) 受益期变更：是否有证据支持变更、对当期摊销的影响\n"
        "3) 提前终止/转销：是否存在需提前终止摊销的项目\n"
        "4) 费用资本化：是否存在将当期费用不当资本化的情况\n"
        "5) 跨期摊销：摊销是否跨越正确的会计期间\n"
        "6) 减值迹象：是否存在账面价值高于可收回金额的迹象"
    ),
    "adj-note": (
        "请生成I4长期待摊费用审定表的审计说明，分析科目1801的变动情况。"
        "需涵盖：期初到期末的变动分析（新增/摊销/减少的构成）、"
        "摊销政策是否一贯执行、大额变动的原因说明、"
        "未审数与审定数的差异说明（有无调整事项）。"
    ),
    "adj-conclusion": (
        "请生成I4长期待摊费用审定表的审计结论，评价：\n"
        "1) 存在性（待摊项目是否实际存在且仍在受益期内）\n"
        "2) 完整性（是否所有应记录的待摊项目均已入账）\n"
        "3) 计价准确性（摊销计算是否正确、期末余额是否准确）\n"
        "4) 列报恰当性（流动/非流动分类是否正确）\n"
        "说明审定数与试算平衡表是否一致、是否存在需调整事项。"
    ),
    "disclosure-narrative": (
        "请生成长期待摊费用附注披露的文字描述部分，包括：\n"
        "1) 长期待摊费用的会计政策说明（确认条件、摊销方法）\n"
        "2) 各类别长期待摊费用的明细（装修费/开办费/改良/大修等）\n"
        "3) 本期增减变动情况（期初/增加/摊销/其他减少/期末）\n"
        "4) 摊销方法和摊销期限说明\n"
        "5) 重大项目的单独披露"
    ),
}


@router.post("/api/workpapers/{wp_id}/i4/ai-generate")
async def i4_ai_generate(
    wp_id: str,
    body: I4AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> I4AiGenerateResponse:
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
        return I4AiGenerateResponse(content="", sources=[])
    return I4AiGenerateResponse(content=result, sources=[])


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
        logger.warning("I4 AI: project context 加载失败: %s", e)
    return ctx
