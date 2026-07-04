"""F2 计价/跌价组 — AI 辅助生成."""

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

router = APIRouter(tags=["f2-val-ai"])


class F2ValAiRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class F2ValAiResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED = {
    "valuation-conclusion",
    "impairment-evaluation",
    "reversal-evaluation",
    "fairness-evaluation",
    "cost-analysis",
    "labor-analysis",
    "inspection-conclusion",
}

_PROMPTS: dict[str, str] = {
    "valuation-conclusion": "请生成F2-38~40计价测试的总体审计结论。",
    "impairment-evaluation": "请生成F2-47跌价准备NRV测试的审计评价结论。",
    "reversal-evaluation": "请生成F2-49跌价转回的审计评价结论。",
    "fairness-evaluation": "请生成F2-52关联采购公允性评价结论。",
    "cost-analysis": "请生成F2-41~44生产成本分析的审计结论。",
    "labor-analysis": "请生成F2-42直接人工分析的审计结论。",
    "inspection-conclusion": "请生成存货检查表(F2-33~35)的审计结论。",
}

_SYSTEM = """你是一位资深注册会计师，协助编制F2存货计价/跌价/检查底稿。
输出中文审计专业用语，直接输出正文，简洁适合底稿。"""


@router.post("/api/workpapers/{wp_id}/f2-val/ai-generate")
async def f2_val_ai_generate(
    wp_id: str,
    body: F2ValAiRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> F2ValAiResponse:
    if not getattr(settings, "WP_AI_SERVICE_ENABLED", True):
        raise HTTPException(503, "AI 服务未启用")
    if body.section not in _SUPPORTED:
        raise HTTPException(400, f"不支持的 section: {body.section}")

    ctx = await _load_ctx(wp_id, db)
    parts = [f"## 任务\n{_PROMPTS.get(body.section, '请生成审计文本。')}\n"]
    if ctx.get("client_name"):
        parts.append(f"客户：{ctx['client_name']}  年度：{ctx.get('audit_year', '')}\n")
    if body.relatedContext:
        lines = "\n".join(f"- {k}: {v}" for k, v in body.relatedContext.items() if v is not None)
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
        return F2ValAiResponse(content="", sources=[])
    return F2ValAiResponse(content=result, sources=[])


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
        logger.warning("F2 val AI context: %s", e)
    return {}
