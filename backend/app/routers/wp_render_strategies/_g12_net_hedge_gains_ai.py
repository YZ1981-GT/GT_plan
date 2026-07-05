"""G12 净敞口套期收益 — AI 辅助端点.

POST /api/workpapers/{wp_id}/g12/ai/{section}
sections: adjudication-analysis / hedge-effectiveness-conclusion /
          net-position-conclusion / voucher-conclusion
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

router = APIRouter(tags=["g12-ai"])
_AI_TIMEOUT = 30.0


class G12AiGenerateRequest(BaseModel):
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class G12AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SYSTEM = """你是一位资深注册会计师，协助编制 G12《净敞口套期收益》审计底稿。
科目6103净敞口套期收益/损失（贷方/损益类），关注套期有效性、净敞口头寸与公允价值测试。
输出：中文、审计专业用语、简洁适合底稿。"""

_PROMPTS = {
    "adjudication-analysis": "请生成 G12-1 审定表审计说明，评价净敞口套期收益本期与上期变动及主要原因。",
    "hedge-effectiveness-conclusion": "请生成 G12-4 公允价值测试与套期有效性测试的审计结论说明。",
    "net-position-conclusion": "请生成 G12-5 风险净敞口检查表的综合审计结论说明。",
    "voucher-conclusion": "请生成 G12-6 凭证检查表的抽样与异常凭证审计结论说明。",
}


@router.post("/workpapers/{wp_id}/g12/ai/{section}", response_model=G12AiGenerateResponse)
async def generate_g12_ai(
    wp_id: str,
    section: str,
    body: G12AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> G12AiGenerateResponse:
    if section not in _PROMPTS:
        raise HTTPException(status_code=404, detail=f"Unknown section: {section}")

    context_snippet = ""
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE 'G12%' LIMIT 50"
            ),
            {"wp_id": wp_id},
        )
        rows = result.fetchall()
        if rows:
            context_snippet = "\n".join(
                f"{r.item_id}: {r.remark[:200] if r.remark else ''}" for r in rows[:10]
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("G12 AI context load failed: %s", e)

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
        logger.exception("G12 AI failed")
        raise HTTPException(status_code=500, detail=str(e)) from e

    return G12AiGenerateResponse(content=content or "", sources=["G12 checklist_responses"])
