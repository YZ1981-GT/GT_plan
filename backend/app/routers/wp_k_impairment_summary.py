"""K 管理循环 — K-F8 K11 资产减值损失跨循环汇总引擎

POST /api/projects/{project_id}/workpapers/{wp_id}/k11/impairment-summary

跨循环汇总减值数据：
  - H1-14 固定资产减值（来自 wp_h_impairment / parsed_data.impairment_calcs）
  - I3 商誉减值（来自 wp_i_goodwill_impairment / parsed_data.goodwill_impairment_calcs）
  - G14 信用减值损失（来自 G ECL 计算）
  - F2 存货跌价（来自 wp_f_impairment / parsed_data.impairment_calcs）

汇总类规则时机铁律：
  - K11 已保存 + 至少 1 个来源底稿已保存 → 触发汇总
  - 全部来源未保存 → sources_missing 列表记录，不阻断（返回已找到的部分）

写回模式：parsed_data.impairment_summary[sheet] = {applied_at, data}
is_llm_stub 由 settings.WP_AI_SERVICE_ENABLED 驱动。

对应 spec：workpaper-k-admin-cycle K-F8 / ADR-K5
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.deps import require_project_access

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers/{wp_id}/k11",
    tags=["wp-k-impairment-summary"],
)


# ─── Input / Output Schemas ───────────────────────────────────────────────────


class ImpairmentSummaryRequest(BaseModel):
    """K11 资产减值损失汇总请求"""

    year: int = Field(..., ge=2000, le=2100, description="年度")
    apply_to_sheet: str | None = Field(
        None,
        description="若给出 sheet 名，则将结果写回 parsed_data.impairment_summary[sheet]",
    )


class ImpairmentByType(BaseModel):
    asset_type: str
    amount: float
    source_wp: str
    source_sheet: str | None = None


class ImpairmentSummaryResponse(BaseModel):
    impairment_by_type: list[ImpairmentByType]
    total_impairment: float
    sources_found: list[str]
    sources_missing: list[str]
    summary: str
    is_llm_stub: bool
    applied_to_sheet: str | None = None
    applied_at: str | None = None
    # K-4 解释链字段（task 4.2 / ADR-6）
    reasoning: str | None = None
    references: list[dict] = Field(default_factory=list)
    data_sources: list[str] = Field(default_factory=list)
    confidence: float = 0.0


def _build_impairment_reasoning(
    total: float,
    sources_found: list[str],
    sources_missing: list[str],
    is_llm_stub: bool,
) -> str:
    """K11 减值汇总推理文本（test 仅校验关键 token 存在性）"""
    if total > 0:
        amount_str = f"{total:,.2f}"
        suffix = (
            "（LLM 暂未启用，已降级为规则汇总结果）"
            if is_llm_stub
            else "（结合 LLM 智能分析）"
        )
        return (
            f"K11 资产减值汇总规则：合计金额 {amount_str}，"
            f"匹配 {len(sources_found)} 个来源底稿，"
            f"{len(sources_missing)} 个来源待补充。{suffix}"
        )
    suffix = (
        "（LLM 暂未启用，已降级为规则结果）"
        if is_llm_stub
        else "（结合 LLM 智能分析）"
    )
    return (
        f"暂无来源底稿提供减值数据，"
        f"建议优先完成 H1 / I3 / G14 / F2 减值底稿{suffix}"
    )


# ─── Cross-cycle Source Lookup ────────────────────────────────────────────────


# 4 类资产减值来源映射（design.md ADR-K5）
IMPAIRMENT_SOURCES = [
    {
        "asset_type": "固定资产减值",
        "wp_code": "H1",
        "namespace": "impairment_calcs",
        "default_sheet_pattern": "减值测算表H1-14",
    },
    {
        "asset_type": "商誉减值",
        "wp_code": "I3",
        "namespace": "goodwill_impairment_calcs",
        "default_sheet_pattern": "减值测试I3-6",
    },
    {
        "asset_type": "信用减值损失",
        "wp_code": "G14",
        "namespace": "ecl_calcs",
        "default_sheet_pattern": "审定表G14-1",
    },
    {
        "asset_type": "存货跌价",
        "wp_code": "F2",
        "namespace": "impairment_calcs",
        "default_sheet_pattern": "存货跌价准备F2-47",
    },
]


async def _lookup_impairment_amount(
    db: AsyncSession, project_id: str, wp_code: str, namespace: str
) -> tuple[float, str | None]:
    """从指定 wp_code 的 parsed_data.{namespace} 读取减值金额

    通过 WpIndex 联表查询找到对应的 WorkingPaper（wp_code 在 WpIndex 上）。

    Returns: (amount, source_sheet_name) 或 (0.0, None) 若未找到
    """
    from app.models.workpaper_models import WorkingPaper, WpIndex

    try:
        proj_uuid = UUID(project_id)
    except Exception:
        return 0.0, None

    res = await db.execute(
        sa.select(WorkingPaper)
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.project_id == proj_uuid,
            WpIndex.wp_code == wp_code,
        )
    )
    wp = res.scalar_one_or_none()
    if wp is None:
        return 0.0, None

    pd = wp.parsed_data or {}
    if not isinstance(pd, dict):
        return 0.0, None

    namespace_data = pd.get(namespace, {})
    if not isinstance(namespace_data, dict) or not namespace_data:
        return 0.0, None

    # 取所有 sheet 的 impairment_amount 累加
    total = 0.0
    first_sheet: str | None = None
    for sheet_name, calc_data in namespace_data.items():
        if not isinstance(calc_data, dict):
            continue
        # 数据结构兼容多种字段名（适配各 spec 不同 namespace）
        data = calc_data.get("data", calc_data)
        amount = (
            data.get("impairment_amount")
            or data.get("total_impairment")
            or data.get("impairment_loss")
            or data.get("ecl_amount")
            or 0.0
        )
        try:
            amount_float = float(amount)
        except (TypeError, ValueError):
            amount_float = 0.0
        total += amount_float
        if first_sheet is None and amount_float > 0:
            first_sheet = sheet_name
    return total, first_sheet


# ─── Main Endpoint ────────────────────────────────────────────────────────────


@router.post("/impairment-summary", response_model=ImpairmentSummaryResponse)
async def k11_impairment_summary(
    project_id: str,
    wp_id: str,
    payload: ImpairmentSummaryRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_project_access("edit")),
) -> ImpairmentSummaryResponse:
    """K-F8 K11 资产减值损失跨循环汇总

    业务约束：
    - 来源底稿全部未保存 → sources_missing 记录，不阻断（汇总类时机铁律）
    - is_llm_stub 由 settings.WP_AI_SERVICE_ENABLED 驱动
    - 支持 apply_to_sheet 写回
    """
    try:
        UUID(project_id)
    except Exception:
        raise HTTPException(400, "invalid project_id")

    impairment_by_type: list[dict[str, Any]] = []
    sources_found: list[str] = []
    sources_missing: list[str] = []
    total_impairment = 0.0

    for src in IMPAIRMENT_SOURCES:
        amount, sheet = await _lookup_impairment_amount(
            db, project_id, src["wp_code"], src["namespace"]
        )
        if amount > 0 and sheet is not None:
            impairment_by_type.append(
                {
                    "asset_type": src["asset_type"],
                    "amount": amount,
                    "source_wp": src["wp_code"],
                    "source_sheet": sheet,
                }
            )
            sources_found.append(f"{src['wp_code']}.{sheet}")
            total_impairment += amount
        else:
            sources_missing.append(
                f"{src['wp_code']} {src['asset_type']}（来源底稿未保存或无减值数据）"
            )

    is_llm_stub = not getattr(settings, "WP_AI_SERVICE_ENABLED", False)

    suffix = "（待 wp_ai_service 接入 LLM 智能分析）" if is_llm_stub else ""
    summary = (
        f"K11 资产减值汇总：合计 ¥{total_impairment:,.2f}，"
        f"来源 {len(sources_found)}/{len(IMPAIRMENT_SOURCES)} 个底稿"
        f"（{len(sources_missing)} 个未提供数据）{suffix}"
    )

    # 写回
    applied_to_sheet = None
    applied_at = None
    if payload.apply_to_sheet:
        result_data = {
            "impairment_by_type": impairment_by_type,
            "total_impairment": total_impairment,
            "sources_found": sources_found,
            "sources_missing": sources_missing,
            "summary": summary,
            "year": payload.year,
        }
        applied_to_sheet = await _maybe_apply_summary_to_workpaper(
            db, wp_id, payload.apply_to_sheet, result_data
        )
        if applied_to_sheet:
            applied_at = datetime.now(timezone.utc).isoformat()

    return ImpairmentSummaryResponse(
        impairment_by_type=[ImpairmentByType(**item) for item in impairment_by_type],
        total_impairment=total_impairment,
        sources_found=sources_found,
        sources_missing=sources_missing,
        summary=summary,
        is_llm_stub=is_llm_stub,
        applied_to_sheet=applied_to_sheet,
        applied_at=applied_at,
    )


# ─── Write-back Helper ────────────────────────────────────────────────────────


async def _maybe_apply_summary_to_workpaper(
    db: AsyncSession, wp_id: str, sheet: str, data: dict[str, Any]
) -> str | None:
    """把减值汇总结果写回 working_paper.parsed_data.impairment_summary[sheet]"""
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
    pd.setdefault("impairment_summary", {})
    pd["impairment_summary"][sheet] = {
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }
    wp.parsed_data = pd
    await db.flush()
    await db.commit()
    return sheet
