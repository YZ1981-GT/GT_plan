"""D4 营业收入 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/d4/ai-generate
Body: { section: string, existingContent: string, relatedContext: object }

支持 sections:
- adj-note / adj-conclusion: 审定表说明/结论
- revenue-change: 收入变动分析
- policy-evaluation: 政策评价
- analysis-note: 分析程序说明
- return-analysis: 退货分析
- related-price: 关联方价格评价
- interview-questions: 访谈问题建议
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.llm_client import chat_completion

logger = logging.getLogger(__name__)

router = APIRouter(tags=["d4-ai"])


# ═══════════════════════════════════════════════════════════════════════════════
# Request / Response
# ═══════════════════════════════════════════════════════════════════════════════


class D4AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class D4AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


# ═══════════════════════════════════════════════════════════════════════════════
# 支持的 section 列表及对应 prompt 模板
# ═══════════════════════════════════════════════════════════════════════════════

_SUPPORTED_SECTIONS = {
    "adj-note",
    "adj-conclusion",
    "revenue-change",
    "policy-evaluation",
    "analysis-note",
    "return-analysis",
    "related-price",
    "interview-questions",
    # ── 8 个附注披露文本域（前端 D4TabDisclosureListed note-1~8 / Soe note-1~7）──
    "d4-disc-note-1",
    "d4-disc-note-2",
    "d4-disc-note-3",
    "d4-disc-note-4",
    "d4-disc-note-5",
    "d4-disc-note-6",
    "d4-disc-note-7",
    "d4-disc-note-8",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 D4《营业收入》。
你需要根据提供的底稿数据和审计准则要求，生成专业、简洁、可直接使用的审计文本。

输出要求：
- 语言：中文
- 风格：审计专业用语，客观陈述事实和结论
- 如需引用具体数据但无法获取，使用 [待填] 占位
- 直接输出正文内容，不要输出标题
- 简洁明了，适合审计底稿使用"""

_SECTION_PROMPTS: dict[str, str] = {
    "adj-note": "请生成D4-1审定表的审计说明，基于收入变动数据和分析程序结果，说明本期营业收入审定情况。",
    "adj-conclusion": "请生成D4-1审定表的审计结论，综合审计程序结果给出结论性意见。",
    "revenue-change": "请分析各产品/项目收入变动原因，基于月度波动趋势和同比变动数据生成变动原因分析。",
    "policy-evaluation": "请基于被审计单位实际情况和CAS14收入准则五步法要求，评价其收入确认会计政策的恰当性。",
    "analysis-note": "请基于分析程序结果（指标异常项），生成分析程序审计说明。",
    "return-analysis": "请基于退货明细数据（客户集中度/时间集中度/金额趋势），分析退货风险并给出评价。",
    "related-price": "请基于关联方与非关联方交易价格对比数据，评价关联方销售价格的公允性。",
    "interview-questions": "请基于项目背景和客户信息，生成客户走访访谈的建议问题清单（涵盖交易真实性、业务实质、资金流向等）。",
    # ── 8 个附注披露文本域 prompt（每条 ≥20 字 + 「不得虚构」）─────────────────
    "d4-disc-note-1": (
        "撰写（1）营业收入和营业成本主表的附注说明。依据审定表 D4-1 的主营业务收入/成本与"
        "其他业务收入/成本本期与上期数据，说明构成与变动原因。不得虚构未提供的数据或事实。"
    ),
    "d4-disc-note-2": (
        "撰写（2）按行业（或产品类型）划分的营业收入与营业成本说明。依据各行业/产品的本期与上期"
        "收入及成本数据，说明各板块收入贡献占比与变动趋势。不得虚构未提供的数据或事实。"
    ),
    "d4-disc-note-3": (
        "撰写（3）按地区划分的营业收入与营业成本说明。依据各地区的本期与上期收入及成本数据，"
        "说明地区分布特征及变动原因（如新市场拓展、区域经济变化等）。不得虚构未提供的数据或事实。"
    ),
    "d4-disc-note-4": (
        "撰写（4）收入分解信息的说明。依据按商品转让时间维度划分的分解信息表，说明各类别收入的"
        "确认时点或时段选择依据、占比情况及变动。不得虚构未提供的数据或事实。"
    ),
    "d4-disc-note-5": (
        "撰写（5）履约义务相关信息的说明。依据 CAS14 收入准则，说明履行履约义务的时间、重要"
        "支付条款、企业承诺转让商品的性质、代理人判断、退款类似义务与质量保证义务。"
        "不得虚构未提供的合同条款或交易安排。"
    ),
    "d4-disc-note-6": (
        "撰写（6）与剩余履约义务有关的信息的说明。依据 CAS14 披露要求，说明分摊至尚未履行的"
        "履约义务的交易价格总额及预计确认为收入的时间安排；如采用简化操作方法（原合同期限不超过"
        "一年或已开票金额可代表已履约价值），应提供定性说明。不得虚构未提供的合同金额或时间安排。"
    ),
    "d4-disc-note-7": (
        "撰写（7）重大合同变更或重大交易价格调整的说明。依据实际发生的合同变更事项，说明变更"
        "内容、会计处理方法（作为单独合同还是现有合同的组成部分）及对收入确认的影响金额。"
        "不得虚构未提供的合同变更事项或金额。"
    ),
    "d4-disc-note-8": (
        "撰写（8）试运行销售收入的说明。依据准则解释第 15 号，说明固定资产试运行收入与研发样品"
        "销售收入的确认依据、金额构成及相关成本抵减情况。不得虚构未提供的试运行数据或金额。"
    ),
}


# ═══════════════════════════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/api/workpapers/{wp_id}/d4/ai-generate")
async def d4_ai_generate(
    wp_id: str,
    body: D4AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> D4AiGenerateResponse:
    """D4 营业收入 AI 辅助生成"""

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

    # 4. 检查降级
    if isinstance(result, str) and result.startswith("["):
        return D4AiGenerateResponse(content="", sources=[])

    return D4AiGenerateResponse(content=result, sources=[])


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

    # Section 指导
    section_guidance = _SECTION_PROMPTS.get(section, "请生成审计底稿文本。")
    parts.append(f"## 任务\n{section_guidance}\n")

    # 项目信息
    ctx_lines = []
    if project_context.get("client_name"):
        ctx_lines.append(f"客户名称：{project_context['client_name']}")
    if project_context.get("audit_year"):
        ctx_lines.append(f"审计年度：{project_context['audit_year']}年")
    if project_context.get("business_category"):
        ctx_lines.append(f"业务类别：{project_context['business_category']}")
    if ctx_lines:
        parts.append("## 项目信息\n" + "\n".join(ctx_lines) + "\n")

    # 相关数据上下文
    if related_context:
        ctx_str = "\n".join(f"- {k}: {v}" for k, v in related_context.items() if v)
        if ctx_str:
            parts.append(f"## 底稿数据\n{ctx_str}\n")

    # 已有内容
    if existing_content:
        parts.append(f"## 已有内容（请补充完善）\n{existing_content[:2000]}\n")
        parts.append("请基于以上信息补充完善已有内容。保留合理部分，纠正不当表述。")
    else:
        parts.append("请根据以上信息生成专业初稿。")

    return "\n".join(parts)


async def _load_project_context(wp_id: str, db: AsyncSession) -> dict:
    """从 working_paper → project 获取上下文"""
    import sqlalchemy as sa

    ctx: dict = {
        "client_name": "",
        "audit_year": "",
        "business_category": "",
    }
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
        logger.warning("D4 AI: project context 加载失败: %s", e)
    return ctx
