"""F2 存货监盘 — AI 辅助生成."""

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

router = APIRouter(tags=["f2-st-ai"])

_SUPPORTED = {
    "stocktake-questionnaire",
    "stocktake-plan",
    "stocktake-summary",
    "stocktake-reconcile",
    "stocktake-sample",
    "stocktake-rollforward",
}

_PROMPTS: dict[str, str] = {
    "stocktake-questionnaire": "请生成 F2-21 存货监盘计划问卷的总体结论（地点覆盖、时间安排、风险应对）。",
    "stocktake-plan": "请生成 F2-22 存货监盘计划底稿（范围、团队分工、程序要点、特别关注事项）。",
    "stocktake-summary": "请生成 F2-23 存货监盘小结（监盘概况、覆盖率、差异分析、观察事项、总体结论）。",
    "stocktake-reconcile": "请生成 F2-24 账面余额与仓储台账核对的审计结论。",
    "stocktake-sample": "请生成 F2-25 抽盘结果汇总的审计结论（差异规模、原因、调整建议）。",
    "stocktake-rollforward": "请生成 F2-26 盘点倒轧表的审计结论（截止准确性、差异调查）。",
}

_SYSTEM = """你是一位资深注册会计师，协助编制 F2 存货监盘系列底稿。
输出中文审计专业用语，直接输出正文，简洁适合底稿。"""


class F2StAiRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class F2StAiResponse(BaseModel):
    content: str
    sources: list[str] = []


@router.post("/api/workpapers/{wp_id}/f2-st/ai-generate")
async def f2_stocktake_ai_generate(
    wp_id: str,
    body: F2StAiRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> F2StAiResponse:
    if not getattr(settings, "WP_AI_SERVICE_ENABLED", True):
        raise HTTPException(503, "AI 服务未启用")
    if body.section not in _SUPPORTED:
        raise HTTPException(400, f"不支持的 section: {body.section}")

    ctx = await _load_ctx(wp_id, db)
    parts = [f"## 任务\n{_PROMPTS.get(body.section, '请生成监盘审计文本。')}\n"]
    if ctx.get("client_name"):
        parts.append(f"客户：{ctx['client_name']}  年度：{ctx.get('audit_year', '')}\n")
    if body.relatedContext:
        lines = "\n".join(
            f"- {k}: {v}" for k, v in body.relatedContext.items() if v is not None
        )
        if lines:
            parts.append(f"## 底稿数据\n{lines}\n")
    if body.existingContent:
        parts.append(f"## 已有内容\n{body.existingContent[:2000]}\n请补充完善。")
    else:
        parts.append("请根据以上信息生成专业初稿。")

    result = await chat_completion(
        messages=[{"role": "system", "content": _SYSTEM}, {"role": "user", "content": "\n".join(parts)}],
        temperature=0.3,
        max_tokens=2000,
    )
    if isinstance(result, str) and result.startswith("["):
        return F2StAiResponse(content="", sources=[])
    return F2StAiResponse(content=result, sources=[])


async def _load_ctx(wp_id: str, db: AsyncSession) -> dict:
    try:
        r = await db.execute(
            sa.text("""
                SELECT p.client_name, p.audit_year FROM working_paper wp
                JOIN projects p ON wp.project_id = p.id WHERE wp.id = :wp_id
            """),
            {"wp_id": wp_id},
        )
        row = r.fetchone()
        if row:
            return {"client_name": row.client_name or "", "audit_year": str(row.audit_year or "")}
    except Exception as e:
        logger.warning("F2 stocktake AI context: %s", e)
    return {}
