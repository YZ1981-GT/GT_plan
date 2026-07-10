"""L0 债务循环函证 — AI 辅助生成端点.

POST /api/workpapers/{wp_id}/l0/ai/{section}

sections:
- alternative-audit-note       → L0-5 替代程序审计说明
- alternative-audit-conclusion → L0-5 替代程序审计结论
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

router = APIRouter(tags=["l0-ai"])


class L0AiGenerateRequest(BaseModel):
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class L0AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "alternative-audit-note",
    "alternative-audit-conclusion",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 L0《债务循环函证》。
科目覆盖：短期借款(2001)、长期借款(2501)、应付债券(2502)、长期应付款(2801)。
核心关注：未回函的金融机构/债权人替代程序（期后还款检查、借款合同/银行对账单支持性证据、
本期借款检查、抵质押/担保证据）；对账差异分析；
期后还款检查比例评价；与L1~L5科目信息交叉核对。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "alternative-audit-note": (
        "请生成债务循环函证替代程序检查表的审计说明，描述对未回函的金融机构/债权人执行的替代程序范围、"
        "抽样方法、检查证据类型（借款合同/银行对账单/还款审批单/银行回单/到账凭证/抵质押合同/担保合同/他项权证等），"
        "以及期后还款检查比例、抵质押证据覆盖比例的计算依据。"
    ),
    "alternative-audit-conclusion": (
        "请生成债务循环函证替代程序检查表的审计结论，评价替代程序所获取证据的充分适当性，"
        "对短期借款/长期借款/应付债券/长期应付款的存在性、完整性、计价与权利义务作出结论。"
    ),
}


@router.post("/api/workpapers/{wp_id}/l0/ai/{section}")
async def l0_ai_generate(
    wp_id: str,
    section: str,
    body: L0AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> L0AiGenerateResponse:
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
    result = await chat_completion(messages=messages, temperature=0.3, max_tokens=2000)
    if isinstance(result, str) and result.startswith("["):
        return L0AiGenerateResponse(content="", sources=[])
    return L0AiGenerateResponse(content=result, sources=[])


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
        logger.warning("L0 AI: project context 加载失败: %s", e)
    return ctx
