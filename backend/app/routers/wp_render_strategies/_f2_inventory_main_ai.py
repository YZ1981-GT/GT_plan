"""F2 存货核心组 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/f2/ai-generate
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

router = APIRouter(tags=["f2-ai"])


class F2AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class F2AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "adj-note",
    "adj-conclusion",
    "analysis-conclusion",
    "cutoff-conclusion",
    "policy-evaluation",
    "production-sales-conclusion",
    "cost-comparison-conclusion",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 F2《存货》。
科目1401~1412存货，借方/资产类。核心关注：收发存核对、计价测试、跌价准备、截止测试、库龄分析。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "adj-note": "请生成F2-1存货审定表的审计说明，涵盖存货总体状况、主要审计程序及发现。",
    "adj-conclusion": "请生成F2-1存货审定表的审计结论，评价存货账面价值是否公允反映。",
    "analysis-conclusion": "请生成F2-18存货总体分析的审计结论，涵盖结构、周转、趋势及异常识别。",
    "cutoff-conclusion": "请生成F2-29~32截止测试的总体审计结论。",
    "policy-evaluation": "请生成F2-16会计政策的审计评价结论。",
    "production-sales-conclusion": "请生成F2-19产销量变动分析结论，关注产销率及库存平衡。",
    "cost-comparison-conclusion": "请生成F2-20产品成本比较分析结论，关注异常变动。",
}


@router.post("/api/workpapers/{wp_id}/f2/ai-generate")
async def f2_ai_generate(
    wp_id: str,
    body: F2AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> F2AiGenerateResponse:
    if not getattr(settings, "WP_AI_SERVICE_ENABLED", True):
        raise HTTPException(503, "AI 服务未启用")
    if body.section not in _SUPPORTED_SECTIONS:
        raise HTTPException(400, f"不支持的 section: {body.section}")

    project_context = await _load_project_context(wp_id, db)
    user_prompt = _build_user_prompt(body.section, body.existingContent, body.relatedContext, project_context)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    result = await chat_completion(messages=messages, temperature=0.3, max_tokens=2000)
    if isinstance(result, str) and result.startswith("["):
        return F2AiGenerateResponse(content="", sources=[])
    return F2AiGenerateResponse(content=result, sources=[])


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
        logger.warning("F2 AI: project context 加载失败: %s", e)
    return ctx
