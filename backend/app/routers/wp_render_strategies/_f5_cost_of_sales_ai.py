"""F5 营业成本 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/f5/ai-generate

sections: cost-analysis / comparison-conclusion / quantity-reconciliation /
          rollforward-evaluation / adjustment-evaluation
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

router = APIRouter(tags=["f5-ai"])


class F5AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class F5AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "cost-analysis",
    "comparison-conclusion",
    "quantity-reconciliation",
    "rollforward-evaluation",
    "adjustment-evaluation",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 F5《营业成本》。
科目6401营业成本，借方/损益类（发生额，无期初期末概念，本期与上期对比）。
核心关注：成本倒轧逻辑（期初材料+购入-期末-其他=投入+人工+制造=完工=营业成本）、
销售数量与结转成本数量核对、毛利率变动分析、月度成本波动、重大成本调整合规性。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "cost-analysis": "请生成F5-3其他业务成本的审计说明，分析成本构成、变动率异常项及与对应收入的配比合理性。",
    "comparison-conclusion": "请生成F5-5与上年度比较分析的审计结论，评价毛利率变动、收入成本匹配性及异常品种的原因合理性。",
    "quantity-reconciliation": "请生成F5-6销售数量与结转成本数量核对的审计说明，分析数量差异、理论结转量偏差及差异原因分类的合理性。",
    "rollforward-evaluation": "请生成F5-7成本倒轧表的审计结论，评价材料流转→成本构成→成本结转→营业成本各环节的勾稽关系及与审定营业成本的差异。",
    "adjustment-evaluation": "请生成F5-8重大调整核查的审计评价，评估重大成本调整事项的原因合理性、审批依据充分性及列报适当性。",
}


@router.post("/api/workpapers/{wp_id}/f5/ai-generate")
async def f5_ai_generate(
    wp_id: str,
    body: F5AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> F5AiGenerateResponse:
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
        return F5AiGenerateResponse(content="", sources=[])
    return F5AiGenerateResponse(content=result, sources=[])


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
    except Exception as e:
        logger.warning("F5 AI: project context 加载失败: %s", e)
    return ctx
