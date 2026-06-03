"""G 投资循环 — G-F11 金融资产分类辅助 API（CAS 22 / IFRS 9）

POST /api/projects/{project_id}/workpapers/{wp_id}/g1/classification-check

输入：business_model（持有以收取/既收取又出售/其他）+ sppi_result（pass/fail）
输出：classification_suggestion + reasoning + is_llm_stub

CAS 22 / IFRS 9 三档分类决策树：
- (hold_to_collect, SPPI pass)  → 摊余成本（amortized_cost）
- (hold_and_sell, SPPI pass)    → FVOCI（公允价值计量且其变动计入其他综合收益）
- (other, *)  OR  (*, SPPI fail) → FVTPL（公允价值计量且其变动计入当期损益）

适用底稿：G1-8 业务模式分析 / G1-10 SPPI 测试。

is_llm_stub = not settings.WP_AI_SERVICE_ENABLED（reasoning 详细解释待 wp_ai_service 接入）。

对应 spec: workpaper-g-investment-cycle G-F11
对应 task: Sprint 3 Task 3.1
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.deps import require_project_access

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers/{wp_id}/g1",
    tags=["wp-g-classification"],
)


# ─── Input / Output Schemas ───────────────────────────────────────────────────


BusinessModel = Literal["hold_to_collect", "hold_and_sell", "other"]
SPPIResult = Literal["pass", "fail"]


class ClassificationCheckRequest(BaseModel):
    """金融资产分类辅助请求"""

    business_model: BusinessModel = Field(
        ...,
        description="业务模式：hold_to_collect=持有以收取合同现金流量 / hold_and_sell=既持有也出售 / other=其他",
    )
    sppi_result: SPPIResult = Field(
        ...,
        description="SPPI 测试结果：pass=合同现金流仅为本金和利息 / fail=不符合 SPPI",
    )
    instrument_name: str | None = Field(
        None,
        description="可选：金融工具名称，用于结果文本展示",
    )

    apply_to_sheet: str | None = Field(
        None,
        description="若给出 sheet 名，则将结果写回 working_paper.parsed_data.classification_checks[sheet]",
    )


class ClassificationCheckResponse(BaseModel):
    """金融资产分类辅助响应"""

    business_model: str
    sppi_result: str
    classification_suggestion: str  # amortized_cost / fvoci / fvtpl
    classification_label_zh: str  # 中文展示标签
    reasoning: str  # 推理说明（含 stub 提示）
    is_llm_stub: bool
    applied_to_sheet: str | None = None


# ─── Classification Logic ─────────────────────────────────────────────────────


def _classify(business_model: str, sppi_result: str) -> tuple[str, str]:
    """CAS 22 / IFRS 9 决策树：(business_model, sppi_result) → (suggestion_code, label_zh)"""
    # SPPI fail OR business_model='other' → FVTPL（覆盖 hold_to_collect/hold_and_sell + SPPI fail）
    if sppi_result == "fail" or business_model == "other":
        return ("fvtpl", "以公允价值计量且其变动计入当期损益的金融资产（FVTPL）")
    # SPPI pass + 'hold_to_collect' → 摊余成本
    if business_model == "hold_to_collect":
        return ("amortized_cost", "以摊余成本计量的金融资产")
    # SPPI pass + 'hold_and_sell' → FVOCI
    if business_model == "hold_and_sell":
        return ("fvoci", "以公允价值计量且其变动计入其他综合收益的金融资产（FVOCI）")
    # 兜底（不应到达，pydantic Literal 已拦截）
    return ("fvtpl", "以公允价值计量且其变动计入当期损益的金融资产（FVTPL）")


def _build_reasoning(
    business_model: str,
    sppi_result: str,
    suggestion: str,
    instrument_name: str | None,
    is_llm_stub: bool,
) -> str:
    """构造推理文本（含 stub 提示）"""
    inst = instrument_name or "该金融资产"

    business_model_zh = {
        "hold_to_collect": "持有以收取合同现金流量",
        "hold_and_sell": "既持有以收取合同现金流量，也以出售为目的",
        "other": "其他业务模式（交易性持有等）",
    }[business_model]

    sppi_zh = "合同现金流量仅为本金和利息（SPPI 通过）" if sppi_result == "pass" else "合同现金流量不符合 SPPI"

    decision_path = {
        "amortized_cost": "业务模式 = 持有收取 ∧ SPPI 通过 → 以摊余成本计量",
        "fvoci": "业务模式 = 既收取又出售 ∧ SPPI 通过 → 以公允价值计量且其变动计入其他综合收益（FVOCI）",
        "fvtpl": "SPPI 不通过 OR 业务模式 = 其他 → 以公允价值计量且其变动计入当期损益（FVTPL）",
    }.get(suggestion, "")

    text = (
        f"针对 {inst} 的金融资产分类辅助分析（CAS 22 / IFRS 9）：\n"
        f"• 业务模式：{business_model_zh}\n"
        f"• SPPI 测试：{sppi_zh}\n"
        f"• 决策路径：{decision_path}"
    )
    if is_llm_stub:
        text += "\n• 提示：当前为纯逻辑判断，详细推理及风险揭示待 wp_ai_service 接入"
    return text


# ─── Main Endpoint ────────────────────────────────────────────────────────────


@router.post("/classification-check", response_model=ClassificationCheckResponse)
async def g1_classification_check(
    project_id: str,
    wp_id: str,
    payload: ClassificationCheckRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_project_access("edit")),
) -> ClassificationCheckResponse:
    """G-F11 金融资产分类辅助（CAS 22 / IFRS 9 决策树）

    is_llm_stub = not settings.WP_AI_SERVICE_ENABLED（reasoning 详尽推理待 LLM 接入）。
    """
    try:
        UUID(project_id)
    except Exception as exc:
        raise HTTPException(400, "invalid project_id") from exc

    is_llm_stub = not settings.WP_AI_SERVICE_ENABLED

    suggestion, label_zh = _classify(payload.business_model, payload.sppi_result)
    reasoning = _build_reasoning(
        payload.business_model,
        payload.sppi_result,
        suggestion,
        payload.instrument_name,
        is_llm_stub,
    )

    applied_to_sheet = await _maybe_apply_classification_to_workpaper(
        db, wp_id, payload, suggestion, label_zh, reasoning, is_llm_stub,
    )

    return ClassificationCheckResponse(
        business_model=payload.business_model,
        sppi_result=payload.sppi_result,
        classification_suggestion=suggestion,
        classification_label_zh=label_zh,
        reasoning=reasoning,
        is_llm_stub=is_llm_stub,
        applied_to_sheet=applied_to_sheet,
    )


# ─── Write-back Helper ────────────────────────────────────────────────────────


async def _maybe_apply_classification_to_workpaper(
    db: AsyncSession,
    wp_id: str,
    payload: ClassificationCheckRequest,
    suggestion: str,
    label_zh: str,
    reasoning: str,
    is_llm_stub: bool,
) -> str | None:
    """若 apply_to_sheet 给出则把分类辅助结果写回 working_paper.parsed_data。

    数据结构（与 fair_value_tests / ecl_calcs 命名空间对称）：
      parsed_data.classification_checks[sheet] = {
        "business_model": "...",
        "sppi_result": "pass|fail",
        "classification_suggestion": "amortized_cost|fvoci|fvtpl",
        "classification_label_zh": "...",
        "reasoning": "...",
        "is_llm_stub": bool,
        "applied_at": ISO8601,
        "instrument_name": "..." | null,
      }
    """
    if not payload.apply_to_sheet:
        return None

    from datetime import datetime, timezone

    from app.models.workpaper_models import WorkingPaper

    try:
        wp_uuid = UUID(wp_id)
    except Exception:
        return None

    res = await db.execute(sa.select(WorkingPaper).where(WorkingPaper.id == wp_uuid))
    wp = res.scalar_one_or_none()
    if wp is None:
        return None

    pd = wp.parsed_data or {}
    if not isinstance(pd, dict):
        pd = {}
    pd.setdefault("classification_checks", {})
    pd["classification_checks"][payload.apply_to_sheet] = {
        "business_model": payload.business_model,
        "sppi_result": payload.sppi_result,
        "classification_suggestion": suggestion,
        "classification_label_zh": label_zh,
        "reasoning": reasoning,
        "is_llm_stub": is_llm_stub,
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "instrument_name": payload.instrument_name,
    }
    wp.parsed_data = pd
    await db.flush()
    await db.commit()
    from app.services.wp_parsed_data_service import touch_after_parsed_data_commit

    await touch_after_parsed_data_commit(wp, source="wp_g_classification")
    return payload.apply_to_sheet
