"""K1 其他应收款 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/k1/ai-generate

sections: policy-check / large-amount-eval / overdue-eval / overall-opinion
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

router = APIRouter(tags=["k1-ai"])


class K1AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class K1AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "policy-check",
    "large-amount-eval",
    "overdue-eval",
    "overall-opinion",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 K1《其他应收款》。
科目1221其他应收款（借方/资产类）+ 坏账准备（贷方/资产备抵类）。
核心关注：资产类三角勾稽（期末=期初+借方-贷方）、坏账准备备抵类（期末=期初+贷方-借方）、
ECL三阶段划分引擎（正常/显著增加/已减值）、坏账准备测算（账龄分析+迁徙率+ECL=EAD×PD×LGD）、
大额其他应收款分析、长期未收回款项评价、关联方检查。
CAS22金融工具确认和计量：ECL预期信用损失模型（12个月/整个存续期）；
CAS24套期会计不适用；减值三阶段（Stage1正常→Stage2信用风险显著增加→Stage3已减值）。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "policy-check": (
        "请生成K1-6信用减值损失会计政策检查的审计师评价，逐项评价被审计单位对其他应收款的"
        "ECL模型选择、账龄组合划分标准、预期损失率确定依据（历史违约率+前瞻性调整）、"
        "三阶段划分标准（信用风险显著增加的判定条件）、减值准备的计提/转回/核销政策。"
        "请结合CAS22和CAS24相关准则要求进行评价。"
    ),
    "large-amount-eval": (
        "请生成K1-5大额其他应收款情况分析表的审计评价，对重要性水平以上的其他应收款逐笔分析"
        "形成原因、款项性质（往来/暂付/其他）、预计收回时间、收回可能性评估、"
        "后续核查措施的充分性。重点关注：是否存在资金占用、关联方非经营性往来、"
        "超期未收回的信用风险升级信号。"
    ),
    "overdue-eval": (
        "请生成K1-10长期未收回款项检查表的审计评价，分析长期挂账其他应收款的账龄分布、"
        "欠款单位偿债能力变化、已采取的催收措施、预计可收回金额评估。"
        "评价是否需要升级ECL阶段（Stage1→Stage2或Stage3）、是否需要补提坏账准备、"
        "是否存在需要核销的已确认无法收回款项。"
    ),
    "overall-opinion": (
        "请生成K1-1审定表底部的审计综合意见，综合评价其他应收款科目整体的存在性、"
        "完整性、计价和分摊（坏账准备充分性）、权利和义务、列报与披露的恰当性。"
        "说明是否发现需要调整的重大事项，审定数与未审数的主要差异原因，"
        "对报表层面影响的结论。"
    ),
}


@router.post("/api/workpapers/{wp_id}/k1/ai-generate")
async def k1_ai_generate(
    wp_id: str,
    body: K1AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> K1AiGenerateResponse:
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
        return K1AiGenerateResponse(content="", sources=[])
    return K1AiGenerateResponse(content=result, sources=[])


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
        logger.warning("K1 AI: project context 加载失败: %s", e)
    return ctx
