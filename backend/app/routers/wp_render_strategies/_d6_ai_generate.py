"""D6 合同资产 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/d6/ai-generate
Body: { section: string, existingContent: string, relatedContext: object }

支持 16 个 sections:
- adj-explanation / adj-impairment-eval / adj-long-term / adj-conclusion
- detail-change / detail-aging / detail-post-settlement
- impairment-explanation / ecl-explanation / ecl-conclusion
- policy-eval-1 / policy-eval-2 / policy-eval-3 / policy-eval-4
- related-party / inspection / writeoff / disclosure-note
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

router = APIRouter(tags=["d6-ai"])


# ═══════════════════════════════════════════════════════════════════════════════
# Request / Response
# ═══════════════════════════════════════════════════════════════════════════════


class D6AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class D6AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


# ═══════════════════════════════════════════════════════════════════════════════
# 支持的 section 及 prompt 模板
# ═══════════════════════════════════════════════════════════════════════════════

_SUPPORTED_SECTIONS = {
    "adj-explanation", "adj-impairment-eval", "adj-long-term", "adj-conclusion",
    "detail-change", "detail-aging", "detail-post-settlement",
    "impairment-explanation", "ecl-explanation", "ecl-conclusion",
    "policy-eval-1", "policy-eval-2", "policy-eval-3", "policy-eval-4",
    "related-party", "inspection", "writeoff", "disclosure-note",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 D6《合同资产》。
你需要根据提供的底稿数据和审计准则要求，生成专业、简洁、可直接使用的审计文本。

科目特征：1402 合同资产，借方科目/资产类。
核心公式：期末=期初+借方-贷方；净值=原值-坏账准备；应计提=余额×损失率。
三区块审定表：一、合同资产原值 / 二、合同资产坏账准备 / 三、合同资产净值（净值=原值-坏账准备）
ECL减值：单项计提 + 账龄组合计提（多组合×6账龄段）

输出要求：
- 语言：中文
- 风格：审计专业用语，客观陈述事实和结论
- 如需引用具体数据但无法获取，使用 [待填] 占位
- 直接输出正文内容，不要输出标题
- 简洁明了，适合审计底稿使用"""

_SECTION_PROMPTS: dict[str, str] = {
    "adj-explanation": "请生成D6-1审定表的'审计说明'（变动分析），基于合同资产三区块期初期末变动数据分析变动合理性。",
    "adj-impairment-eval": "请生成D6-1审定表的'减值计提充分性评价'，综合ECL测算结果、账龄分布、客户信用状况评价坏账准备计提的充分性。",
    "adj-long-term": "请生成D6-1审定表的'长期挂账原因分析'，对账龄超过1年的合同资产分析长期未结转原因及风险。",
    "adj-conclusion": "请生成D6-1审定表的'审计结论'，综合审计程序结果对合同资产余额的真实性、计价准确性、列报适当性给出结论。",
    "detail-change": "请分析D6-2明细表各合同的变动原因，基于期初期末审定数变动情况分析。",
    "detail-aging": "请分析D6-2明细表的账龄分布情况，关注长账龄合同资产的风险。",
    "detail-post-settlement": "请分析D6-2明细表的期后结转情况，评估期后回收对减值评估的影响。",
    "impairment-explanation": "请生成D6-3减值准备明细表的审计说明，分析本期计提/转回/核销的合理性。",
    "ecl-explanation": "请生成D6-8减值测算的审计说明，评价预期信用损失率的合理性和前瞻性信息的考量。",
    "ecl-conclusion": "请生成D6-8减值测算的审计结论，综合单项和组合测算结果评价减值准备的充分性。",
    "policy-eval-1": "请评价被审计单位合同资产减值计提政策的合规性，对比CAS22金融工具确认和计量准则要求。",
    "policy-eval-2": "请分析被审计单位历史坏账损失情况，评价其ECL模型的预测准确性。",
    "policy-eval-3": "请评价被审计单位在ECL模型中考虑的前瞻性信息（宏观经济、行业趋势等）的适当性。",
    "policy-eval-4": "请与同行业公司的ECL计提政策进行对比分析，评价被审计单位政策的合理性。",
    "related-party": "请生成D6-5关联方检查的审计说明，分析关联方合同资产余额的商业合理性和定价公允性。",
    "inspection": "请生成D6-6检查表的审计说明，基于抽样检查结果评价合同资产的真实性和完整性。",
    "writeoff": "请生成D6-9转回核销检查的审计说明，评价本期坏账准备转回/核销的合规性和充分性。",
    "disclosure-note": "请生成附注披露的审计说明，评价合同资产相关附注披露的完整性和准确性。",
}


# ═══════════════════════════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/api/workpapers/{wp_id}/d6/ai-generate")
async def d6_ai_generate(
    wp_id: str,
    body: D6AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> D6AiGenerateResponse:
    """D6 合同资产 AI 辅助生成"""

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
        return D6AiGenerateResponse(content="", sources=[])

    return D6AiGenerateResponse(content=result, sources=[])


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
        logger.warning("D6 AI: project context 加载失败: %s", e)
    return ctx
