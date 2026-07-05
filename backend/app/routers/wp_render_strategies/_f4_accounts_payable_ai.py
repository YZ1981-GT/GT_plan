"""F4 应付账款 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/f4/ai-generate

sections: substantive-analysis / long-outstanding / related-evaluation /
          unrecorded-conclusion / voucher-check / financing-evaluation
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

router = APIRouter(tags=["f4-ai"])


class F4AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class F4AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "substantive-analysis",
    "long-outstanding",
    "related-evaluation",
    "unrecorded-conclusion",
    "voucher-check",
    "financing-evaluation",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 F4《应付账款》。
科目2202应付账款，贷方/负债类。核心关注：长期挂账风险、未入账负债（反向截止测试）、关联方集中度、供应商融资合规性。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "substantive-analysis": "请生成F4-4实质性分析程序的审计结论，评价应付账款余额变动合理性及趋势分析结果。",
    "long-outstanding": "请生成F4-5长期挂账检查的审计评价，分析1年以上应付账款的挂账原因、是否需转营业外收入及风险评估。",
    "related-evaluation": "请生成F4-6关联方应付账款检查的审计说明，评价集中度、结算方式及定价公允性。",
    "unrecorded-conclusion": "请生成F4-7未入账检查（反向截止测试）的审计结论，评价期后采购/入库/收票中是否存在应入当期但未入账的应付款项。",
    "voucher-check": "请生成F4-8应付账款检查表的总体审计结论，综合评价借方（付款）和贷方（采购）抽凭检查结果。",
    "financing-evaluation": "请生成F4-9供应商融资检查的审计评价，评估保理/票据融资/供应链融资的列报适当性和终止确认合规性。",
}


@router.post("/api/workpapers/{wp_id}/f4/ai-generate")
async def f4_ai_generate(
    wp_id: str,
    body: F4AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> F4AiGenerateResponse:
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
        return F4AiGenerateResponse(content="", sources=[])
    return F4AiGenerateResponse(content=result, sources=[])


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
        logger.warning("F4 AI: project context 加载失败: %s", e)
    return ctx
