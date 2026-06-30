"""D3 预收账款 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/d3/ai-generate
Body: { section: string, existingContent: string, relatedContext: object }

支持 sections:
- adj-aging-reason: 超1年原因说明
- adj-change-analysis: 变动分析
- adj-conclusion: 审定表结论
- detail-change: 明细变动原因
- detail-contract: 合同匹配情况
- detail-longterm: 超1年未结转原因
- analysis-note: 分析程序说明
- longterm-reason: 长期挂账原因建议
- related-party-note: 关联方审计说明
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.llm_client import chat_completion

logger = logging.getLogger(__name__)

router = APIRouter(tags=["d3-ai"])


# ═══════════════════════════════════════════════════════════════════════════════
# Request / Response
# ═══════════════════════════════════════════════════════════════════════════════


class D3AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class D3AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


# ═══════════════════════════════════════════════════════════════════════════════
# 支持的 section 及 prompt 模板
# ═══════════════════════════════════════════════════════════════════════════════

_SUPPORTED_SECTIONS = {
    "adj-aging-reason",
    "adj-change-analysis",
    "adj-conclusion",
    "detail-change",
    "detail-contract",
    "detail-longterm",
    "analysis-note",
    "longterm-reason",
    "related-party-note",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 D3《预收账款》。
你需要根据提供的底稿数据和审计准则要求，生成专业、简洁、可直接使用的审计文本。

科目特征：2203 预收账款，贷方科目/负债类。核心关注：期后结转、长期挂账追踪、款项性质分类、CAS14收入准则联动。

输出要求：
- 语言：中文
- 风格：审计专业用语，客观陈述事实和结论
- 如需引用具体数据但无法获取，使用 [待填] 占位
- 直接输出正文内容，不要输出标题
- 简洁明了，适合审计底稿使用"""

_SECTION_PROMPTS: dict[str, str] = {
    "adj-aging-reason": "请生成D3-1审定表的'账龄超过1年的预收账款原因说明'，基于长期挂账客户明细和项目背景。",
    "adj-change-analysis": "请生成D3-1审定表的'预收账款变动分析'，基于期初期末数据变动和主要客户变动情况。",
    "adj-conclusion": "请生成D3-1审定表的审计结论，综合审计程序结果对预收账款余额真实性/完整性/列报给出结论。",
    "detail-change": "请分析明细表D3-2各客户预收账款期末变动原因，基于借贷发生额和客户集中度情况。",
    "detail-contract": "请生成预收账款与合同匹配情况说明，分析已收款但未履约的合同状态和预计转收入时点。",
    "detail-longterm": "请生成超1年未结转预收账款的原因说明，结合CAS14收入确认五步法分析合同不成立的合理性。",
    "analysis-note": "请基于D3-4分析程序结果（借贷发生额分析+Top5债务人），生成分析程序审计说明。",
    "longterm-reason": "请为该客户长期挂账的预收账款生成未结转原因建议文本，结合项目背景和行业惯例。",
    "related-party-note": "请生成关联方预收账款审计说明，评价关联方交易的合理性和定价公允性。",
}


# ═══════════════════════════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/api/workpapers/{wp_id}/d3/ai-generate")
async def d3_ai_generate(
    wp_id: str,
    body: D3AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> D3AiGenerateResponse:
    """D3 预收账款 AI 辅助生成"""

    if not getattr(settings, "WP_AI_SERVICE_ENABLED", True):
        raise HTTPException(503, "AI 服务未启用")

    if body.section not in _SUPPORTED_SECTIONS:
        raise HTTPException(
            400,
            f"不支持的 section: {body.section}。支持: {sorted(_SUPPORTED_SECTIONS)}",
        )

    # 1. 加载项目上下文
    project_context = await _load_project_context(wp_id, db)

    # 2. 构造 user prompt
    user_prompt = _build_user_prompt(
        section=body.section,
        existing_content=body.existingContent,
        related_context=body.relatedContext,
        project_context=project_context,
    )

    # 3. 调用 LLM
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    result = await chat_completion(
        messages=messages,
        temperature=0.3,
        max_tokens=2000,
    )

    if isinstance(result, str) and result.startswith("["):
        return D3AiGenerateResponse(content="", sources=[])

    return D3AiGenerateResponse(content=result, sources=[])


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════


def _build_user_prompt(
    section: str,
    existing_content: str,
    related_context: dict[str, Any],
    project_context: dict,
) -> str:
    parts: list[str] = []

    section_guidance = _SECTION_PROMPTS.get(section, "请生成审计底稿文本。")
    parts.append(f"## 任务\n{section_guidance}\n")

    ctx_lines = []
    if project_context.get("client_name"):
        ctx_lines.append(f"客户名称：{project_context['client_name']}")
    if project_context.get("audit_year"):
        ctx_lines.append(f"审计年度：{project_context['audit_year']}年")
    if project_context.get("business_category"):
        ctx_lines.append(f"业务类别：{project_context['business_category']}")
    if ctx_lines:
        parts.append("## 项目信息\n" + "\n".join(ctx_lines) + "\n")

    if related_context:
        ctx_str = "\n".join(f"- {k}: {v}" for k, v in related_context.items() if v)
        if ctx_str:
            parts.append(f"## 底稿数据\n{ctx_str}\n")

    if existing_content:
        parts.append(f"## 已有内容（请补充完善）\n{existing_content[:2000]}\n")
        parts.append("请基于以上信息补充完善已有内容。保留合理部分，纠正不当表述。")
    else:
        parts.append("请根据以上信息生成专业初稿。")

    return "\n".join(parts)


async def _load_project_context(wp_id: str, db: AsyncSession) -> dict:
    """从 working_paper → project 获取上下文"""
    import sqlalchemy as sa

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
        logger.warning("D3 AI: project context 加载失败: %s", e)
    return ctx
