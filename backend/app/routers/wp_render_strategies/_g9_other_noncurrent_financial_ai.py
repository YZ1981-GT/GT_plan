"""G9 其他非流动金融资产 — AI 辅助端点.

POST /api/workpapers/{wp_id}/g9/ai/{section}
sections: adjudication-analysis / adjudication-conclusion /
          detail-note / detail-conclusion / adjustment-note / adjustment-conclusion /
          fair-value-conclusion / fair-value-note /
          l3-reconciliation-conclusion / l3-note /
          voucher-conclusion / voucher-note /
          disclosure-note / disclosure-conclusion / disclosure-section
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
    "adjudication-conclusion": "请根据 G9-1 审定表，按 A/B/C 口径生成总体审计结论。",
    "detail-note": "请根据 G9-2 明细表，生成审计说明：概述明细核对、分类计量恰当性、与 G9-1 勾稽及拟调整事项。",
    "detail-conclusion": "请根据 G9-2 明细表，按 A/B/C 口径生成审计结论。",
    "adjustment-note": "请根据 G9-3 调整分录，生成审计说明：概述调整依据、借贷平衡及回写审定表影响。",
    "adjustment-conclusion": "请根据 G9-3 调整分录，按 A/B/C 口径生成审计结论。",
    "fair-value-conclusion": "请根据 G9-4 公允价值测试表，生成公允价值计量审计结论。",
    "fair-value-note": "请根据 G9-4 公允价值测试表，生成审计说明：概述取数来源、层次划分、估值技术与不可观察输入值核对及差异分析。",
    "l3-reconciliation-conclusion": "请根据 G9-5 第三层次调节表 10 因子变动分析，生成 L3 审计结论。",
    "l3-note": "请根据 G9-5 第三层次调节表，生成审计说明：概述十因子取数、层次转入转出原因、公式期末与企业报告勾稽、仍持有未实现及披露恰当性。",
    "voucher-conclusion": "请根据 G9-6 凭证检查表异常样本与抽样覆盖情况，生成凭证测试结论（含对存在/计价等认定的影响）。",
    "voucher-note": "请根据 G9-6 凭证检查表，生成审计说明：概述抽样方法与样本量、六项核对（原始/授权/账务/分类/公允价值/减值）执行情况、异常与跨期处理。",
    "disclosure-note": "请根据 G9 附注披露核对结果，生成审计说明：概述披露完整性、列报格式及与审定数勾稽。",
    "disclosure-conclusion": "请根据 G9 附注披露核对结果，按 A/B/C 口径生成审计结论。",
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
        raise HTTPException(status_code=500, detail=str(e)) from e
    return G9AiGenerateResponse(content=content or "")
