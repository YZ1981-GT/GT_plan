"""G10 交易性金融负债 — AI 辅助端点.

POST /api/workpapers/{wp_id}/g10/ai/{section}
sections: adjudication-analysis / classification-conclusion / fair-value-conclusion /
          derivative-conclusion / voucher-conclusion
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

router = APIRouter(tags=["g10-ai"])
_AI_TIMEOUT = 30.0


class G10AiGenerateRequest(BaseModel):
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    variant: str = ""


class G10AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SYSTEM = """你是一位资深注册会计师，协助编制 G10《交易性金融负债》审计底稿。
科目2101交易性金融负债（贷方/负债类），关注公允价值计量、分类适当性、衍生工具核查与凭证测试结论。
输出：中文、审计专业用语、简洁适合底稿。"""

_PROMPTS = {
    "adjudication-analysis": "请生成 G10-1 审定表审计说明，分析各负债项目期初期末变动及主要原因。",
    "classification-conclusion": "请根据 G10-4 分类适当性检查问卷，生成综合审计结论。",
    "fair-value-conclusion": "请根据 G10-5 公允价值测试表，生成公允价值计量审计结论。",
    "derivative-conclusion": "请根据 G10-8 衍生金融工具核查问卷，生成衍生工具审计结论。",
    "voucher-conclusion": "请根据 G10-7 凭证检查表异常样本，生成凭证测试结论。",
}


@router.post("/api/workpapers/{wp_id}/g10/ai/{section}", response_model=G10AiGenerateResponse)
async def generate_g10_ai(
    wp_id: str,
    section: str,
    body: G10AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> G10AiGenerateResponse:
    if section not in _PROMPTS:
        raise HTTPException(status_code=404, detail=f"Unknown section: {section}")

    context_snippet = ""
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, remark, conclusion FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE 'G10%' LIMIT 60"
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
        logger.warning("G10 AI context load failed: %s", e)

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
        logger.exception("G10 AI failed")
        raise HTTPException(status_code=500, detail=str(e)) from e

    return G10AiGenerateResponse(content=content or "", sources=["G10 checklist_responses"])
