"""I2 开发支出 — CAS6资本化判断引擎端点

POST /api/workpapers/{wp_id}/i2/capitalization/evaluate → CAS6五条件评估结果
POST /api/workpapers/{wp_id}/i2/capitalization/validate-split → 费用化+资本化=总额校验

纯函数实现（与前端 useI2CapitalizationEngine.ts 对等逻辑）
CAS6第9条资本化五条件：
- ① 技术可行性
- ② 完成意图
- ③ 使用或出售能力
- ④ 未来经济利益
- ⑤ 资源充足（技术/财务/其他）
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["i2-capitalization"])


# ═══════════════════════════════════════════════════════════════════════════════
# 纯函数：CAS6资本化判断引擎（与前端 useI2CapitalizationEngine.ts 对等）
# ═══════════════════════════════════════════════════════════════════════════════

_CAS6_CONDITION_NAMES = {
    1: "技术可行性",
    2: "完成意图",
    3: "使用或出售能力",
    4: "未来经济利益",
    5: "资源充足",
}


def evaluate_capitalization(conditions: list[dict[str, Any]]) -> dict:
    """CAS6五条件评估.

    Args:
        conditions: [{id: 1-5, result: 'yes'|'no'|'na', evidence: str}]
    Returns:
        {isMet: bool, missingConditions: list[int], conclusion: str}
    """
    missing: list[int] = []
    for cond in conditions:
        cond_id = cond.get("id", 0)
        result = cond.get("result", "")
        if result == "no":
            missing.append(cond_id)

    is_met = len(missing) == 0
    if is_met:
        conclusion = "满足资本化条件：CAS6第9条五项条件均已满足，可确认为无形资产。"
    else:
        missing_names = [_CAS6_CONDITION_NAMES.get(m, f"条件{m}") for m in missing]
        conclusion = f"不满足资本化条件：缺失{','.join(missing_names)}，开发支出应费用化处理。"

    return {
        "isMet": is_met,
        "missingConditions": missing,
        "conclusion": conclusion,
    }


def validate_research_split(expense_i6: float, capitalized_i2: float, total_budget: float) -> dict:
    """验证费用化+资本化拆分是否合理（VR-I6-01）.

    Args:
        expense_i6: I6研发费用（费用化金额）
        capitalized_i2: I2开发支出（资本化金额）
        total_budget: 研发总额预算
    Returns:
        {isValid: bool, difference: float}
    """
    actual_total = expense_i6 + capitalized_i2
    difference = abs(actual_total - total_budget)
    is_valid = difference < 0.01  # 允许1分钱误差
    return {
        "isValid": is_valid,
        "difference": round(actual_total - total_budget, 2),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# API Models
# ═══════════════════════════════════════════════════════════════════════════════

class CAS6ConditionItem(BaseModel):
    id: int = Field(..., ge=1, le=5, description="条件编号1-5")
    result: str = Field(..., pattern=r"^(yes|no|na)$", description="判断结果")
    evidence: str = Field("", description="证据描述")


class CapitalizationEvaluateRequest(BaseModel):
    project_name: str = Field(..., description="研发项目名称")
    conditions: list[CAS6ConditionItem] = Field(..., min_length=1, max_length=5)


class CapitalizationEvaluateResponse(BaseModel):
    isMet: bool
    missingConditions: list[int]
    conclusion: str


class ValidateSplitRequest(BaseModel):
    expense_i6: float = Field(..., description="I6费用化金额")
    capitalized_i2: float = Field(..., description="I2资本化金额")
    total_budget: float = Field(..., description="研发总额预算")


class ValidateSplitResponse(BaseModel):
    isValid: bool
    difference: float


# ═══════════════════════════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/api/workpapers/{wp_id}/i2/capitalization/evaluate",
    response_model=CapitalizationEvaluateResponse,
)
async def i2_capitalization_evaluate(
    wp_id: str,
    body: CapitalizationEvaluateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CapitalizationEvaluateResponse:
    """CAS6五条件资本化评估."""
    conditions_data = [{"id": c.id, "result": c.result, "evidence": c.evidence} for c in body.conditions]
    result = evaluate_capitalization(conditions_data)
    return CapitalizationEvaluateResponse(**result)


@router.post(
    "/api/workpapers/{wp_id}/i2/capitalization/validate-split",
    response_model=ValidateSplitResponse,
)
async def i2_capitalization_validate_split(
    wp_id: str,
    body: ValidateSplitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ValidateSplitResponse:
    """费用化+资本化=研发总额校验（VR-I6-01）."""
    result = validate_research_split(body.expense_i6, body.capitalized_i2, body.total_budget)
    return ValidateSplitResponse(**result)
