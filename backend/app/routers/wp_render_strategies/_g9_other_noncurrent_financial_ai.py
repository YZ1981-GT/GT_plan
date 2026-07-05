"""G9 其他非流动金融资产 — AI 辅助端点.

POST /api/workpapers/{wp_id}/g9/ai/{section}
sections: adjudication-analysis / fair-value-conclusion / l3-reconciliation-conclusion / voucher-conclusion
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

router = APIRouter(tags=["g9-ai"])

_SYSTEM = """你是一位资深注册会计师，协助编制 G9《其他非流动金融资产》审计底稿。
科目1504其他非流动金融资产（借方/资产类），关注混合计量(FVTPL/FVOCI/摊余成本)、公允价值三层次、L3调节表与凭证测试。
输出：中文、审计专业用语、简洁适合底稿。"""

_PROMPTS = {
    "adjudication-analysis": "请生成 G9-1 审定表审计说明，按 FVTPL/FVOCI/摊余成本分组分析期初期末变动。",
    "fair-value-conclusion": "请根据 G9-4 公允价值测试表，生成公允价值计量审计结论。",
    "l3-reconciliation-conclusion": "请根据 G9-5 第三层次调节表 10 因子变动分析，生成 L3 审计结论。",
    "voucher-conclusion": "请根据 G9-6 凭证检查表异常样本，生成凭证测试结论。",
    "disclosure-section": "请为 G9 附注披露单行项目生成专业附注文本（科目1504其他非流动金融资产）。",
}


class G9AiGenerateRequest(BaseModel):
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    variant: str = ""


class G9AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


@router.post("/api/workpapers/{wp_id}/g9/ai/{section}", response_model=G9AiGenerateResponse)
async def generate_g9_ai(
    wp_id: str,
    section: str,
    body: G9AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> G9AiGenerateResponse:
    if section not in _PROMPTS:
        raise HTTPException(status_code=404, detail=f"Unknown G9 AI section: {section}")
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
            feature=f"g9-ai-{section}",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("G9 AI %s failed: %s", section, e)
        content = f"【G9 {section} 审计结论占位】请结合 G9 底稿数据补充专业结论。（AI 暂不可用）"
    return G9AiGenerateResponse(content=content or "", sources=[f"g9/{section}"])
