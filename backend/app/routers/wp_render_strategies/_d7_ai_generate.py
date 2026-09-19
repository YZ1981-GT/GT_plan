"""D7 合同负债 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/d7/ai-generate
Body: { section: string, existingContent: string, relatedContext: object }

支持 9 个 sections:
- adj-explanation / adj-conclusion / adj-aging-explanation
- detail-change / detail-contract / detail-over1year
- analysis-explanation / analysis-conclusion
- longterm-reason
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

router = APIRouter(tags=["d7-ai"])


# ═══════════════════════════════════════════════════════════════════════════════
# Request / Response
# ═══════════════════════════════════════════════════════════════════════════════


class D7AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class D7AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


# ═══════════════════════════════════════════════════════════════════════════════
# 支持的 section 及 prompt 模板
# ═══════════════════════════════════════════════════════════════════════════════

_SUPPORTED_SECTIONS = {
    "adj-explanation", "adj-conclusion", "adj-aging-explanation",
    "detail-change", "detail-contract", "detail-over1year",
    "analysis-explanation", "analysis-conclusion",
    "longterm-reason",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 D7《合同负债》。
你需要根据提供的底稿数据和审计准则要求，生成专业、简洁、可直接使用的审计文本。

科目特征：2205 合同负债，贷方科目/负债类。
核心公式：期末余额 = 期初审定 + 贷方发生 - 借方发生（贷增借减）。
双区块审定表：一、按性质分类（预收货款/开发项目预收款/预收工程款/其他） + 二、按账龄分类（1年以内/1~2年/2~3年/3年以上）
合同负债合计 = 小计 - 计入其他非流动负债的合同负债
CAS14 合同负债 vs 预收账款区分：对已签合同的预收款项确认为合同负债；未签合同的预收确认为预收账款。

输出要求：
- 语言：中文
- 风格：审计专业用语，客观陈述事实和结论
- 如需引用具体数据但无法获取，使用 [待填] 占位
- 直接输出正文内容，不要输出标题
- 简洁明了，适合审计底稿使用"""

_SECTION_PROMPTS: dict[str, str] = {
    "adj-explanation": "请生成D7-1审定表的'审计说明'（变动分析），基于合同负债双区块期初期末变动数据分析变动合理性。重点关注按性质分类各项变动原因。",
    "adj-conclusion": "请生成D7-1审定表的'审计结论'，综合审计程序结果对合同负债余额的真实性、完整性、列报适当性给出结论。",
    "adj-aging-explanation": "请生成D7-1审定表的'账龄说明'，分析按账龄分类区块中各账龄段占比变化及超1年合同负债的合理性。",
    "detail-change": "请分析D7-2明细表各合同的变动原因，基于期初期末审定数变动情况，关注大额变动客户。",
    "detail-contract": "请分析D7-2明细表的合同履行情况，评估合同负债转为收入确认的进度合理性。",
    "detail-over1year": "请分析D7-2明细表中账龄超过1年的合同负债原因，评估是否存在长期挂账风险。",
    "analysis-explanation": "请生成D7-4分析表的'审计说明'，综合借方/贷方发生额分析及Top10债务人集中度分析，评价合同负债变动的合理性。",
    "analysis-conclusion": "请生成D7-4分析表的'审计结论'，基于分析性程序结果，对合同负债整体变动趋势给出审计判断。",
    "longterm-reason": "请为D7-5账龄1年以上检查表生成'未结转原因'说明，逐户分析合同负债长期未结转为收入的原因（如工程未完工/验收未通过/质保期等）。",
}


# ═══════════════════════════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/api/workpapers/{wp_id}/d7/ai-generate")
async def d7_ai_generate(
    wp_id: str,
    body: D7AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> D7AiGenerateResponse:
    """D7 合同负债 AI 辅助生成"""

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
        return D7AiGenerateResponse(content="", sources=[])

    return D7AiGenerateResponse(content=result, sources=[])


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
        logger.warning("D7 AI: project context 加载失败: %s", e)
    return ctx
