"""G0 投资循环函证 — AI 辅助生成端点.

POST /api/workpapers/{wp_id}/g0/ai-generate

sections:
- securities-diff-conclusion   → G0-3(证券) 证券投资差异核对审计结论
- alternative-audit-conclusion → G0-6 投资循环替代程序审计结论
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

router = APIRouter(tags=["g0-ai"])


class G0AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class G0AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "securities-diff-conclusion",
    "alternative-audit-conclusion",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 G0《投资循环函证》。
科目覆盖：交易性金融资产/债权投资/长期股权投资/其他权益工具投资。
核心关注：证券投资函证回函与账面在持仓数量/公允价值/市值三维度的差异核对；
未回函投资项目的替代程序（持仓证明检查/股利收入证据/投资处置收益证据/公允价值佐证）；
差异原因分类（估值时点差异/交易日与结算日差异/计量方法差异）；公允价值 Level1-3 佐证充分性。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "securities-diff-conclusion": (
        "请生成 G0-3(证券) 函证差异核对表的审计结论，评价证券投资回函确认的持仓数量、"
        "单位公允价值、总市值与账面记录的差异，分析差异原因的合理性，并对函证证据的充分适当性作出结论。"
    ),
    "alternative-audit-conclusion": (
        "请生成 G0-6 投资循环替代程序检查表的审计结论，评价对未回函投资项目执行的替代程序"
        "（持仓证明/股利收入/处置收益/公允价值佐证）所获取证据的充分适当性，"
        "对投资的存在性、计价与准确性作出结论。"
    ),
}


@router.post("/api/workpapers/{wp_id}/g0/ai-generate")
async def g0_ai_generate(
    wp_id: str,
    body: G0AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> G0AiGenerateResponse:
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
        return G0AiGenerateResponse(content="", sources=[])
    return G0AiGenerateResponse(content=result, sources=[])


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
        logger.warning("G0 AI: project context 加载失败: %s", e)
    return ctx
