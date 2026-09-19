"""D1 应收票据 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/d1/ai-generate
Body: { section: string, existingContent: string, relatedContext: object }
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

router = APIRouter(tags=["d1-ai"])


class D1AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class D1AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "policy-conclusion",
    "ecl-audit-note",
    "ecl-audit-conclusion",
    "writeoff-audit-note",
    "writeoff-audit-conclusion",
    "memo-audit-note",
    "memo-audit-conclusion",
    "sampling-audit-note",
    "sampling-audit-conclusion",
    "detail-audit-procedures",
    "detail-audit-note",
    "detail-audit-conclusion",
    "baddebt-audit-procedures",
    "baddebt-audit-note",
    "baddebt-audit-conclusion",
    "bm-audit-procedures",
    "bm-audit-note",
    "bm-audit-conclusion",
    "adj-note",
    "adj-conclusion",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 D1《应收票据》。
你需要根据提供的底稿数据和审计准则要求，生成专业、简洁、可直接使用的审计文本。

科目特征：1121 应收票据，流动资产/借方科目。核心关注：业务模式(SPP测试)、备查簿核对、
贴现背书终止确认(CAS23)、预期信用损失、监盘与质押披露。

输出要求：
- 语言：中文
- 风格：审计专业用语，客观陈述事实和结论
- 如需引用具体数据但无法获取，使用 [待填] 占位
- 直接输出正文内容，不要输出标题
- 简洁明了，适合审计底稿使用"""

_SECTION_PROMPTS: dict[str, str] = {
    "policy-conclusion": "请生成D1-14会计政策一致性检查的审计结论，综合评价ECL政策与模型是否合理。",
    "ecl-audit-note": "请生成D1-15坏账准备测算表的审计说明，说明测算过程、与D1-4核对及差异分析。",
    "ecl-audit-conclusion": "请生成D1-15坏账准备测算表的审计结论，对计提充分性给出明确意见。",
    "writeoff-audit-note": "请生成D1-16转回/核销检查的审计说明，包括笔数金额、与D1-4核对及异常关注。",
    "writeoff-audit-conclusion": "请生成D1-16转回/核销检查的审计结论，明确转回/核销是否合理。",
    "memo-audit-note": "请生成D1-7备查簿核对的审计说明，涵盖票据完整性、与明细账核对及贴现背书统计。",
    "memo-audit-conclusion": "请生成D1-7备查簿核对的审计结论。",
    "sampling-audit-note": "请生成D1-13一般检查表的审计说明，涵盖抽样方法、凭证核对结果及期后事项。",
    "sampling-audit-conclusion": "请生成D1-13一般检查表的审计结论。",
    "detail-audit-procedures": (
        "请生成应收票据原值明细表的「审计过程」记录。"
        "若上下文 sheet=D1-3，按客户维度编写；否则按票据种类（D1-2）编写。"
        "按编号列出已执行/拟执行的实质性程序，覆盖：明细账与总账核对、分类/客户核对、"
        "期初审定衔接、本期增减变动抽查、关联方识别（D1-3）、重分类核对（D1-3）、"
        "期末余额与备查簿/监盘勾稽、披露完整性。"
        "语言简洁，可直接填入底稿「二、审计过程」文本框。"
    ),
    "detail-audit-note": (
        "请生成应收票据原值明细表的「审计说明」。"
        "若上下文 sheet=D1-3：说明按客户构成、关联方余额、期初衔接、本期增减、重分类及与总账/D1-2勾稽。"
        "若为 D1-2：说明按票据种类（银行承兑/商业承兑等）的余额构成、期初审定衔接、"
        "本期增减主要变动原因、与总账/备查簿勾稽结果及需关注事项。"
        "可直接填入底稿「三、审计说明」文本框。"
    ),
    "detail-audit-conclusion": (
        "请生成应收票据原值明细表的「审计结论」。"
        "若上下文 sheet=D1-3：明确按客户明细完整性、关联方披露充分性、与总账一致性、是否需调整。"
        "若为 D1-2：明确原值明细是否完整准确、分类是否恰当、与审定表/总账是否一致、是否存在需调整事项。"
        "结论简洁肯定，可直接填入「四、审计结论」。"
    ),
    "baddebt-audit-procedures": (
        "请生成D1-4坏账准备明细表的「审计过程」记录。"
        "按编号列出已执行/拟执行的实质性程序，覆盖：单项/组合分类完整性、期初审定衔接、"
        "本期计提/收回/转回/核销抽查、与D1-15 ECL测算勾稽、与D1-16转回核销勾稽、"
        "期末余额与总账/审定表一致性、披露充分性。"
        "语言简洁，可直接填入底稿「二、审计过程」文本框。"
    ),
    "baddebt-audit-note": (
        "请生成D1-4坏账准备明细表的「审计说明」。"
        "说明按单项/按组合构成、本期计提转回核销主要变动、与D1-15 ECL及D1-16勾稽结果、"
        "差异原因及需关注事项。可直接填入「三、审计说明」。"
    ),
    "baddebt-audit-conclusion": (
        "请生成D1-4坏账准备明细表的「审计结论」。"
        "明确坏账准备计提是否充分、分类是否恰当、与总账/ECL是否一致、是否存在需调整事项。"
        "结论简洁肯定，可直接填入「四、审计结论」。"
    ),
    "bm-audit-procedures": (
        "请生成D1-6应收票据业务模式分析表的「审计过程」记录。"
        "按编号列出已执行/拟执行的程序，覆盖：了解管理层对三组合（高/低信用银行承兑、商业承兑）"
        "的业务模式、观察贴现/背书频率与未来预期、填写分类判断矩阵、与D1-7备查簿及D1-8贴现背书勾稽、"
        "列报项目与D1-1审定表一致性。语言简洁，可直接填入「二、审计过程」。"
    ),
    "bm-audit-note": (
        "请生成D1-6业务模式分析表的「审计说明」。"
        "说明各组合业务模式及依据、分类判断矩阵结论、终止确认考虑、"
        "与D1-7/D1-8勾稽结果及列报分类（应收票据/应收款项融资）判断。可直接填入「三、审计说明」。"
    ),
    "bm-audit-conclusion": (
        "请生成D1-6业务模式分析表的「审计结论」。"
        "明确业务模式判断是否恰当、列报分类是否正确、与审定表是否一致、是否存在需调整事项。"
        "结论简洁肯定，可直接填入「四、审计结论」。"
    ),
    "adj-note": (
        "请生成D1-5应收票据调整分录汇总表的「审计说明」。"
        "汇总各调整事项的原因、对1121应收票据及相关科目的影响、"
        "与D1-1审定表AJE/RJE勾稽情况、是否需要推送A13错报汇总。"
        "可直接填入审计说明文本框。"
    ),
    "adj-conclusion": (
        "请生成D1-5调整分录汇总表的「审计结论」。"
        "明确调整分录是否完整准确、借贷是否平衡、对审定意见的影响、是否需进一步调整。"
        "结论简洁肯定。"
    ),
}


@router.post("/api/workpapers/{wp_id}/d1/ai-generate")
async def d1_ai_generate(
    wp_id: str,
    body: D1AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> D1AiGenerateResponse:
    if not getattr(settings, "WP_AI_SERVICE_ENABLED", True):
        raise HTTPException(503, "AI 服务未启用")

    if body.section not in _SUPPORTED_SECTIONS:
        raise HTTPException(
            400,
            f"不支持的 section: {body.section}。支持: {sorted(_SUPPORTED_SECTIONS)}",
        )

    project_context = await _load_project_context(wp_id, db)
    user_prompt = _build_user_prompt(
        section=body.section,
        existing_content=body.existingContent,
        related_context=body.relatedContext,
        project_context=project_context,
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    result = await chat_completion(
        messages=messages,
        temperature=0.3,
        max_tokens=800,
        enable_thinking=False,
    )

    if isinstance(result, str) and result.startswith("["):
        return D1AiGenerateResponse(content="", sources=[])

    return D1AiGenerateResponse(content=result, sources=[])


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
    if ctx_lines:
        parts.append("## 项目信息\n" + "\n".join(ctx_lines) + "\n")

    if related_context:
        ctx_str = "\n".join(
            f"- {k}: {str(v)[:500]}"
            for k, v in related_context.items()
            if v is not None and str(v).strip()
        )
        if ctx_str:
            parts.append(f"## 底稿数据\n{ctx_str[:3000]}\n")

    if existing_content:
        parts.append(f"## 已有内容（请补充完善）\n{existing_content[:2000]}\n")
        parts.append("请基于以上信息补充完善已有内容。")
    else:
        parts.append("请根据以上信息生成专业初稿。")

    return "\n".join(parts)


async def _load_project_context(wp_id: str, db: AsyncSession) -> dict:
    import sqlalchemy as sa

    ctx: dict = {"client_name": "", "audit_year": ""}
    try:
        result = await db.execute(
            sa.text("""
                SELECT p.client_name, p.audit_year
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
    except Exception as e:
        logger.warning("D1 AI: project context 加载失败: %s", e)
    return ctx
