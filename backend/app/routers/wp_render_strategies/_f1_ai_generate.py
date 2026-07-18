"""F1 预付账款 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/f1/ai-generate
Body: { section: string, existingContent: string, relatedContext: object }

支持 sections:
- adj-change-analysis: 审定表变动分析
- adj-conclusion: 审定表结论
- analysis-note: 分析程序说明（兼容）
- analysis-balance-note / analysis-debit-note / analysis-credit-note / analysis-supplier-note: F1-4 分块说明
- analysis-conclusion: F1-4 审计结论
- longterm-reason: 长期挂账原因/审计说明
- longterm-conclusion: F1-5 审计结论
- related-party-note: F1-6 关联方审计说明
- related-party-conclusion: F1-6 关联方审计结论
- comprehensive-conclusion: 综合检查结论
- detail-prior-linkage: 明细表期初与上年报核对
- detail-fluctuation: 明细表重大变动原因
- detail-over1year: 明细表超1年预付款说明
- detail-conclusion: 明细表审计结论
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

router = APIRouter(tags=["f1-ai"])


# ═══════════════════════════════════════════════════════════════════════════════
# Request / Response
# ═══════════════════════════════════════════════════════════════════════════════


class F1AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class F1AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


# ═══════════════════════════════════════════════════════════════════════════════
# 支持的 section 及 prompt 模板
# ═══════════════════════════════════════════════════════════════════════════════

_SUPPORTED_SECTIONS = {
    "adj-change-analysis",
    "adj-conclusion",
    "analysis-note",
    "analysis-balance-note",
    "analysis-debit-note",
    "analysis-credit-note",
    "analysis-supplier-note",
    "analysis-conclusion",
    "longterm-reason",
    "longterm-conclusion",
    "related-party-note",
    "related-party-conclusion",
    "comprehensive-conclusion",
    "detail-prior-linkage",
    "detail-fluctuation",
    "detail-over1year",
    "detail-conclusion",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 F1《预付账款》。
你需要根据提供的底稿数据和审计准则要求，生成专业、简洁、可直接使用的审计文本。

科目特征：1123 预付账款，借方科目/资产类。核心公式：期末=期初+借方-贷方。
核心关注：预付款项真实性、长期挂款追踪、关联方交易定价公允性、期后到货验证、供应商集中度。

输出要求：
- 语言：中文
- 风格：审计专业用语，客观陈述事实和结论
- 如需引用具体数据但无法获取，使用 [待填] 占位
- 直接输出正文内容，不要输出标题
- 简洁明了，适合审计底稿使用"""

_SECTION_PROMPTS: dict[str, str] = {
    "adj-change-analysis": "请生成F1-1审定表的'预付账款变动分析'，基于期初期末数据变动和主要供应商变动情况。",
    "adj-conclusion": "请生成F1-1审定表的审计结论，综合审计程序结果对预付账款余额真实性/完整性/列报给出结论。",
    "analysis-note": "请基于F1-4分析程序结果（余额/借贷发生额/大额供应商），生成分析性复核审计说明。",
    "analysis-balance-note": "请生成F1-4「预付款项余额分析」审计说明，评价余额结构（存货/费用/工程固定资产/其他）及占存货比重是否合理。",
    "analysis-debit-note": "请生成F1-4「借方发生额分析」审计说明，评价新增预付结构及与存货采购金额的勾稽关系。",
    "analysis-credit-note": "请生成F1-4「贷方发生额分析」审计说明，评价转销路径；对大额收回款项关注合理性与关联方资金占用。",
    "analysis-supplier-note": "请生成F1-4「大额供应商期末余额分析」审计说明，评价商业合理性、交易真实性、账龄及期后结算。",
    "analysis-conclusion": "请生成F1-4实质性分析审计结论（A未见异常 / B除重大调整外未见异常 / C存在重大未调整或范围受限），并简要陈述依据。",
    "longterm-reason": "请生成F1-5账龄1年及以上大额预付检查的审计说明，归纳未结转原因分类、减值与重分类考虑、期后消化情况。",
    "longterm-conclusion": "请生成F1-5审计结论（A未见异常 / B除重大调整外未见异常 / C存在重大未调整或范围受限），并简要陈述依据。",
    "related-party-note": "请生成F1-6关联方预付账款审计说明，评价交易真实性、商业实质、定价公允性、是否存在资金占用及披露充分性。",
    "related-party-conclusion": "请生成F1-6关联方及交易检查审计结论（A未见异常 / B除重大调整外未见异常 / C存在重大未调整或范围受限），并简要陈述依据。",
    "comprehensive-conclusion": "请基于综合检查(F1-7)的抽凭结果和异常发现，生成综合检查审计结论。",
    "detail-prior-linkage": "请生成F1-2明细表审计说明(1)：期初审定余额与上年审计报告/附注披露的勾稽核对说明，如有差异说明原因。",
    "detail-fluctuation": "请生成F1-2明细表审计说明(2)：预付账款本期重大增减变动原因分析（结合主要供应商、款项性质、项目进度）。",
    "detail-over1year": "请生成F1-2明细表审计说明(3)：账龄超过1年的预付款款项性质、未结转/未收回原因及后续处理计划。",
    "detail-conclusion": "请生成F1-2明细表审计结论（可选A未见异常 / B除重大调整外未见异常 / C存在重大未调整或范围受限不可确认），并简要陈述依据。",
}


# ═══════════════════════════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/api/workpapers/{wp_id}/f1/ai-generate")
async def f1_ai_generate(
    wp_id: str,
    body: F1AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> F1AiGenerateResponse:
    """F1 预付账款 AI 辅助生成"""

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
        return F1AiGenerateResponse(content="", sources=[])

    return F1AiGenerateResponse(content=result, sources=[])


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
        logger.warning("F1 AI: project context 加载失败: %s", e)
    return ctx
