"""H0 固定资产循环函证 — AI 辅助生成端点.

POST /api/workpapers/{wp_id}/h0/ai-generate

sections:
- alternative-audit-note       → H0-5 替代程序审计说明
- alternative-audit-conclusion   → H0-5 替代程序审计结论
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

router = APIRouter(tags=["h0-ai"])


class H0AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class H0AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "alternative-audit-note",
    "alternative-audit-conclusion",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 H0《固定资产循环函证》。
科目覆盖：固定资产、在建工程、使用权资产相关购置与权属。
核心关注：未回函被函证单位的替代程序（期后验收/权属证据、期末余额支持性证据、
本期新增资产检查、抵押担保/融资租赁证据）；权属证书与账面记录核对；
新增资产请购审批、到货验收、转固手续完整性；与 H1/L1/L3 抵质押信息交叉核对。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "alternative-audit-note": (
        "请生成 H0-5 固定资产循环替代程序检查表的审计说明，描述对未回函被函证单位执行的替代程序范围、"
        "抽样方法、检查证据类型（验收单/权属证书/采购合同/发票/付款凭证/转固手续/抵押融资租赁合同等），"
        "以及权属证据比例、验收证据比例的计算依据。"
    ),
    "alternative-audit-conclusion": (
        "请生成 H0-5 固定资产循环替代程序检查表的审计结论，评价替代程序所获取证据的充分适当性，"
        "对固定资产的存在性、权属、计价与完整性作出结论。"
    ),
}


@router.post("/api/workpapers/{wp_id}/h0/ai-generate")
async def h0_ai_generate(
    wp_id: str,
    body: H0AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> H0AiGenerateResponse:
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
        return H0AiGenerateResponse(content="", sources=[])
    return H0AiGenerateResponse(content=result, sources=[])


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
        logger.warning("H0 AI: project context 加载失败: %s", e)
    return ctx
