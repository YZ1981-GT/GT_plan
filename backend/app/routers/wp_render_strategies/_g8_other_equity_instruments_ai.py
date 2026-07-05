"""G8 其他权益工具投资 — AI 辅助端点.

POST /api/workpapers/{wp_id}/g8/ai/{section}
sections: adjudication-analysis / fair-value-conclusion / designation-conclusion / voucher-conclusion
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.llm_client import chat_completion

logger = logging.getLogger(__name__)

router = APIRouter(tags=["g8-ai"])

_SYSTEM = """你是一位资深注册会计师，协助编制 G8《其他权益工具投资》审计底稿。
科目1503其他权益工具投资（借方/资产类），关注 FVOCI 指定适当性(CAS22)、公允价值三层次测试与 OCI 核算。
输出：中文、审计专业用语、简洁适合底稿。"""

_PROMPTS = {
    "adjudication-analysis": "请生成 G8-1 审定表审计说明，分析期初期末变动及公允价值计量合理性。",
    "fair-value-conclusion": "请根据 G8-4 公允价值测试表，生成公允价值计量审计结论（含 Level1-3 层次分析）。",
    "designation-conclusion": "请根据 G8-5 指定适当性检查表，生成非交易性权益工具指定 FVOCI 的合规性审计结论。",
    "voucher-conclusion": "请根据 G8-6 凭证检查表异常样本，生成凭证测试结论。",
    "disclosure-section": "请为 G8 附注披露单行项目生成专业附注文本（科目1503其他权益工具投资）。",
}


class G8AiGenerateRequest(BaseModel):
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    variant: str = ""


class G8AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


@router.post("/api/workpapers/{wp_id}/g8/ai/{section}", response_model=G8AiGenerateResponse)
async def generate_g8_ai(
    wp_id: str,
    section: str,
    body: G8AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> G8AiGenerateResponse:
    if section not in _PROMPTS:
        raise HTTPException(status_code=404, detail=f"Unknown G8 AI section: {section}")
    prompt = _PROMPTS[section]
    if section == "disclosure-section":
        label = body.relatedContext.get("label", "")
        if label:
            prompt += f"\n\n项目：{label}"
        if body.relatedContext.get("currentAmount") is not None:
            prompt += f"\n本期金额：{body.relatedContext.get('currentAmount')}"
        if body.relatedContext.get("priorAmount") is not None:
            prompt += f"\n上期金额：{body.relatedContext.get('priorAmount')}"
    if body.existingContent:
        prompt += f"\n\n已有内容：{body.existingContent[:2000]}"
    try:
        content = await chat_completion(
            system=_SYSTEM,
            user=prompt,
            db=db,
            wp_id=wp_id,
            feature=f"g8-ai-{section}",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("G8 AI %s failed: %s", section, e)
        content = f"【G8 {section} 审计结论占位】请结合 G8 底稿数据补充专业结论。（AI 暂不可用）"
    return G8AiGenerateResponse(content=content or "", sources=[f"g8/{section}"])
