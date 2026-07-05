"""G13 公允价值变动收益 — AI 辅助端点.

POST /api/workpapers/{wp_id}/g13/ai/{section}
sections: adjudication-analysis / fv-change-conclusion
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

router = APIRouter(tags=["g13-ai"])
_AI_TIMEOUT = 30.0


class G13AiGenerateRequest(BaseModel):
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class G13AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SYSTEM = """你是一位资深注册会计师，协助编制 G13《公允价值变动收益》审计底稿。
科目6101公允价值变动收益（贷方/损益类），与 G1/G8/G9/G10 公允价值变动数据交叉验证。
关注：FV变动=期末-期初与审定数勾稽、变动合理性、附注披露。
输出：中文、审计专业用语、简洁适合底稿。"""

_PROMPTS = {
    "adjudication-analysis": "请生成 G13-1 审定表审计说明，评价各金融资产/负债类型公允价值变动及主要原因。",
    "fv-change-conclusion": "请生成 G13 附注披露中公允价值变动收益段落的说明文字。",
}


@router.post("/workpapers/{wp_id}/g13/ai/{section}", response_model=G13AiGenerateResponse)
async def generate_g13_ai(
    wp_id: str,
    section: str,
    body: G13AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> G13AiGenerateResponse:
    if section not in _PROMPTS:
        raise HTTPException(status_code=404, detail=f"Unknown section: {section}")

    context_snippet = ""
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE 'G13%' LIMIT 50"
            ),
            {"wp_id": wp_id},
        )
        rows = result.fetchall()
        if rows:
            context_snippet = "\n".join(f"{r.item_id}: {r.remark[:200] if r.remark else ''}" for r in rows[:10])
    except Exception as e:  # noqa: BLE001
        logger.warning("G13 AI context load failed: %s", e)

    user_prompt = (
        f"{_PROMPTS[section]}\n\n"
        f"已有内容：\n{body.existingContent or '（无）'}\n\n"
        f"相关上下文：\n{context_snippet or str(body.relatedContext)}"
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
        logger.exception("G13 AI failed")
        raise HTTPException(status_code=500, detail=str(e)) from e

    return G13AiGenerateResponse(content=content or "", sources=["G13 checklist_responses"])
