"""G11 投资收益 — AI 辅助端点.

POST /api/workpapers/{wp_id}/g11/ai/{section}
sections: adjudication-analysis / return-rate-conclusion / voucher-conclusion
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

router = APIRouter(tags=["g11-ai"])
_AI_TIMEOUT = 30.0


class G11AiGenerateRequest(BaseModel):
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    variant: str = ""


class G11AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SYSTEM = """你是一位资深注册会计师，协助编制 G11《投资收益》审计底稿。
科目6111投资收益（损益类/贷方），关注收益率异常、投资类型变动、凭证核对结论。
输出：中文、审计专业用语、简洁适合底稿。"""

_PROMPTS = {
    "adjudication-analysis": "请生成 G11-1 审定表审计说明，分析各投资类型本期与上期变动及主要原因。",
    "return-rate-conclusion": "请根据收益率分析表中异常波动项目，生成 G11-4 审计结论。",
    "voucher-conclusion": "请根据凭证检查表异常样本，生成投资收益凭证测试结论。",
}


@router.post("/api/workpapers/{wp_id}/g11/ai/{section}", response_model=G11AiGenerateResponse)
async def generate_g11_ai(
    wp_id: str,
    section: str,
    body: G11AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> G11AiGenerateResponse:
    if section not in _PROMPTS:
        raise HTTPException(status_code=404, detail=f"Unknown section: {section}")

    context_snippet = ""
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, remark, conclusion FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE 'G11%' LIMIT 60"
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
        logger.warning("G11 AI context load failed: %s", e)

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
        logger.exception("G11 AI failed")
        raise HTTPException(status_code=500, detail=str(e)) from e

    return G11AiGenerateResponse(content=content or "", sources=["G11 checklist_responses"])
