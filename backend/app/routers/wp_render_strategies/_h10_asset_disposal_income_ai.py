"""H10 资产处置损益 — AI 辅助端点.

POST /api/workpapers/{wp_id}/h10/ai/{section}
sections: adjudication-analysis / disclosure-analysis
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.llm_client import chat_completion

logger = logging.getLogger(__name__)

router = APIRouter(tags=["h10-ai"])
_AI_TIMEOUT = 30.0


class H10AiGenerateRequest(BaseModel):
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    variant: str = ""


class H10AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SYSTEM = """你是一位资深注册会计师，协助编制 H10《资产处置损益》审计底稿。
科目6115资产处置损益（损益类/贷方），关注处置合规、定价合理性、与固定资产清理勾稽。
输出：中文、审计专业用语、简洁适合底稿。"""

_PROMPTS = {
    "adjudication-analysis": "请生成 H10-1 审定表审计说明，分析各类资产处置损益本期与上期变动及主要原因。",
    "disclosure-analysis": "请根据 H10 附注披露各行发生额，生成附注说明段落（含非经常性损益说明如适用）。",
}


@router.post("/api/workpapers/{wp_id}/h10/ai/{section}", response_model=H10AiGenerateResponse)
async def generate_h10_ai(
    wp_id: str,
    section: str,
    body: H10AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> H10AiGenerateResponse:
    if section not in _PROMPTS:
        raise HTTPException(status_code=404, detail=f"Unknown section: {section}")

    context_snippet = ""
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, remark, conclusion FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE 'H10%' LIMIT 60"
            ),
            {"wp_id": wp_id},
        )
        rows = result.fetchall()
        if rows:
            parts = []
            for r in rows[:12]:
                text = (r.remark or r.conclusion or "")[:200]
                parts.append(f"{r.item_id}: {text}")
            context_snippet = "\n".join(parts)
    except Exception as e:  # noqa: BLE001
        logger.warning("H10 AI context load failed: %s", e)

    rows_hint = ""
    if body.rows:
        rows_hint = "\n".join(str(r)[:120] for r in body.rows[:8])

    user_prompt = (
        f"{_PROMPTS[section]}\n\n"
        f"已有内容：\n{body.existingContent or '（无）'}\n\n"
        f"行数据摘要：\n{rows_hint or '（无）'}\n\n"
        f"底稿上下文：\n{context_snippet or str(body.relatedContext)}"
    )

    try:
        content = await asyncio.wait_for(
            chat_completion(
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
            ),
            timeout=_AI_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="AI 生成超时") from None
    except Exception as e:  # noqa: BLE001
        logger.exception("H10 AI failed")
        raise HTTPException(status_code=500, detail=str(e)) from e

    return H10AiGenerateResponse(content=content or "", sources=["H10 checklist_responses"])
