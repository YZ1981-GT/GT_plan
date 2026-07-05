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
        max_tokens=2000,
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
        ctx_str = "\n".join(f"- {k}: {v}" for k, v in related_context.items() if v)
        if ctx_str:
            parts.append(f"## 底稿数据\n{ctx_str}\n")

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
