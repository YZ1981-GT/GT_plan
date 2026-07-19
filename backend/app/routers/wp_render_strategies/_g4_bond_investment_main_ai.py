"""G4 债权投资(main组) — AI 辅助生成端点

POST /api/workpapers/{wp_id}/g4-main/ai/{section}

sections: adjudication-analysis / interest-conclusion / disclosure-text / overall-opinion
"""

from __future__ import annotations

import asyncio
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

router = APIRouter(tags=["g4-main-ai"])

# AI 生成超时（秒）
_AI_TIMEOUT = 30.0


class G4MainAiGenerateRequest(BaseModel):
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class G4MainAiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 G4《债权投资》。
科目1501债权投资（借方/资产类），以摊余成本计量的金融资产（CAS22分类为AC类）。
核心关注：摊余成本三要素分解（成本+利息调整+应计利息）的正确性、
实际利率法利息收入测算的准确性、ECL三阶段划分对计息基数的影响、
一年内到期重分类列报的恰当性、减值准备计提充分性。

审定表三层结构：一、债权投资原值 / 二、减值准备 / 三、摊余成本(=原值-减值)。
借方科目公式：期末未审 = 期初审定 + 借方发生额 - 贷方发生额。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "adjudication-note": (
        "请生成G4-1审定表的审计说明，概述债权投资原值/减值/摊余成本三层结构的审定程序、"
        "与试算勾稽及一年内到期重分类关注事项。"
    ),
    "adjudication-analysis": (
        "请生成G4-1审定表的审计分析，评价债权投资原值/减值准备/摊余成本三层结构"
        "的期末余额变动合理性，分析变动率异常项（|变动率|>20%）的原因，"
        "以及一年内到期重分类列报的恰当性。"
    ),
    "adjudication-conclusion": (
        "请生成G4-1审定表的审计结论，按A/B/C口径评价科目1501审定结果。"
    ),
    "detail-note": (
        "请生成G4-2明细表的审计说明，概述逐笔债权投资明细核对、摊余成本要素"
        "及一年内到期分类关注事项。"
    ),
    "detail-conclusion": (
        "请生成G4-2明细表的审计结论，按A/B/C口径评价明细完整性与计价准确性。"
    ),
    "adjustment-note": (
        "请生成G4-3调整分录的审计说明，概述调整依据、AJE/RJE性质及对审定表影响。"
    ),
    "adjustment-conclusion": (
        "请生成G4-3调整分录的审计结论，评价借贷平衡与依据充分性。"
    ),
    "interest-note": (
        "请生成G4-4利息测算表的审计说明，概述实际利率法测算程序及差异分析。"
    ),
    "interest-conclusion": (
        "请生成G4-4利息测算表的审计结论，评价各投资项目使用实际利率法确认利息收入"
        "的正确性，包括初始入账价值的确定、实际利率的测算依据、"
        "各计息期间利息收入计算的准确性，以及与审定表利息收入的差异分析。"
    ),
    "disclosure-text": (
        "请生成债权投资附注披露文本，包括会计政策描述（摊余成本计量、实际利率法、"
        "减值政策）、期末余额明细（按投资种类/到期日分类）、"
        "本期变动情况（购入/到期/减值）及ECL阶段划分说明。"
    ),
    "disclosure-listed-note": (
        "请生成G4上市公司附注披露说明初稿，按投资种类列示债权投资余额并与审定数勾稽。"
    ),
    "disclosure-soe-note": (
        "请生成G4国企附注披露说明初稿，简要列示债权投资余额及主要构成并与审定数勾稽。"
    ),
    "overall-opinion": (
        "请生成G4债权投资的整体审计意见，综合审定表余额变动分析、利息测算验证结果、"
        "明细表逐笔核对情况、调整分录的合规性各方面，"
        "形成对科目1501列报与披露的总体结论。"
    ),
}

_SUPPORTED_SECTIONS = set(_SECTION_PROMPTS.keys())


@router.post("/api/workpapers/{wp_id}/g4-main/ai/{section}")
async def g4_main_ai_generate(
    wp_id: str,
    section: str,
    body: G4MainAiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> G4MainAiGenerateResponse:
    if not getattr(settings, "WP_AI_SERVICE_ENABLED", True):
        raise HTTPException(503, "AI 服务未启用")
    if section not in _SUPPORTED_SECTIONS:
        raise HTTPException(400, f"不支持的 section: {section}。支持: {sorted(_SUPPORTED_SECTIONS)}")

    project_context = await _load_project_context(wp_id, db)
    user_prompt = _build_user_prompt(section, body.existingContent, body.relatedContext, project_context)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    try:
        result = await asyncio.wait_for(
            chat_completion(messages=messages, temperature=0.3, max_tokens=2000),
            timeout=_AI_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise HTTPException(504, "AI 生成超时（30秒），请重试")
    if isinstance(result, str) and result.startswith("["):
        return G4MainAiGenerateResponse(content="", sources=[])
    return G4MainAiGenerateResponse(content=result, sources=[])


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
    except Exception as e:  # noqa: BLE001
        logger.warning("G4 Main AI: project context 加载失败: %s", e)
    return ctx
