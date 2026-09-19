"""D5 应收款项融资 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/d5/ai-generate
Body: { section: string, existingContent: string, relatedContext: object }

支持 sections:
- adj-explanation: 审定表审计说明
- adj-conclusion: 审定表审计结论
- detail-change: 明细变动原因分析
- fv-rate-analysis: 公允价值贴现利率合理性评价
- fv-conclusion: 公允价值测算结论
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

router = APIRouter(tags=["d5-ai"])


# ═══════════════════════════════════════════════════════════════════════════════
# Request / Response
# ═══════════════════════════════════════════════════════════════════════════════


class D5AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class D5AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


# ═══════════════════════════════════════════════════════════════════════════════
# 支持的 section 及 prompt 模板
# ═══════════════════════════════════════════════════════════════════════════════

_SUPPORTED_SECTIONS = {
    "adj-explanation",
    "adj-conclusion",
    "detail-change",
    "fv-rate-analysis",
    "fv-conclusion",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 D5《应收款项融资》。
你需要根据提供的底稿数据和审计准则要求，生成专业、简洁、可直接使用的审计文本。

科目特征：1124 应收款项融资，借方科目/资产类/以公允价值计量且其变动计入其他综合收益（FVOCI）。
核心关注：公允价值测算（贴现法）、OCI公允价值变动、业务模式判定（收取合同现金流量+出售模式）、
公允价值层次判定（第二/第三层次）、票据贴现利率合理性。

贴现公式：贴现利息 = 票面金额 × 市场贴现利率 × 剩余天数 ÷ 360
公允价值 = 票面金额 - 贴现利息

输出要求：
- 语言：中文
- 风格：审计专业用语，客观陈述事实和结论
- 如需引用具体数据但无法获取，使用 [待填] 占位
- 直接输出正文内容，不要输出标题
- 简洁明了，适合审计底稿使用"""

_SECTION_PROMPTS: dict[str, str] = {
    "adj-explanation": (
        "请生成D5-1审定表的'审计说明'，基于应收款项融资期初期末变动数据、"
        "公允价值测算结果和业务模式判断，分析变动合理性。"
    ),
    "adj-conclusion": (
        "请生成D5-1审定表的'审计结论'，综合审计程序结果对应收款项融资余额的"
        "真实性、公允价值计量准确性、OCI变动合理性、列报适当性给出结论。"
    ),
    "detail-change": (
        "请分析D5-2明细表各项目变动原因，基于期初期末审定数变动情况，"
        "区分应收票据和应收账款两类资产的变动特征和业务背景。"
    ),
    "fv-rate-analysis": (
        "请评价D5-4公允价值测算中使用的市场贴现利率的合理性，"
        "分析利率选取依据（如央行公布的再贴现率、银行同期贴现利率）、"
        "层次判定依据（可观察市场输入→第二层次/不可观察→第三层次），"
        "并评估利率变动对公允价值的敏感性。"
    ),
    "fv-conclusion": (
        "请生成D5-4公允价值测算的审计结论，综合评价贴现法计量结果的合理性、"
        "与期末账面价值的一致性、OCI变动的准确性。"
    ),
}


# ═══════════════════════════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/api/workpapers/{wp_id}/d5/ai-generate")
async def d5_ai_generate(
    wp_id: str,
    body: D5AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> D5AiGenerateResponse:
    """D5 应收款项融资 AI 辅助生成"""

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
        return D5AiGenerateResponse(content="", sources=[])

    return D5AiGenerateResponse(content=result, sources=[])


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
        logger.warning("D5 AI: project context 加载失败: %s", e)
    return ctx
