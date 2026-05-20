"""I 无形资产循环 — I-F5 开发支出资本化时点判断 API

POST /api/projects/{project_id}/workpapers/{wp_id}/i2/capitalization-check

CAS 6 / IAS 38 开发支出资本化 5 条件判断：
    1. technical_feasibility   — 完成该无形资产以使其能够使用或出售在技术上具有可行性
    2. completion_intent       — 具有完成该无形资产并使用或出售的意图
    3. ability_to_use_or_sell  — 无形资产产生经济利益的方式（使用或出售）
    4. future_economic_benefits— 该无形资产存在使用或出售的市场，能够产生经济利益
    5. resource_sufficiency    — 有足够的技术、财务和其他资源支持开发并使用或出售

逻辑：
    Step 1: 5 条件全 True
        → all_conditions_met = True
        → capitalization_start_date = max(condition_dates.values())
        → recommendation = "建议自 YYYY-MM-DD 起将开发阶段支出资本化"
    Step 2: 任一 False
        → all_conditions_met = False
        → missing_conditions = [<未满足条件名称列表>]
        → recommendation = "不满足资本化条件，缺失：..."

对应 spec：workpaper-i-intangible-assets-cycle I-F5
对应 ADR：ADR-I2
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers/{wp_id}/i2",
    tags=["wp-i-capitalization"],
)


# ─── 5 条件名称（与字段一一对应） ─────────────────────────────────────────────


CONDITION_LABELS: dict[str, str] = {
    "technical_feasibility": "技术可行性已论证（CAS 6 第 9 条 (一)）",
    "completion_intent": "具有完成并使用或出售的意图（CAS 6 第 9 条 (二)）",
    "ability_to_use_or_sell": "使用或出售产生经济利益的方式（CAS 6 第 9 条 (三)）",
    "future_economic_benefits": "存在使用或出售市场可产生未来经济利益（CAS 6 第 9 条 (四)）",
    "resource_sufficiency": "技术/财务/其他资源充足（CAS 6 第 9 条 (五)）",
}

CONDITION_FIELDS = list(CONDITION_LABELS.keys())


# ─── Input / Output Schemas ───────────────────────────────────────────────────


class CapitalizationCheckRequest(BaseModel):
    """开发支出资本化时点判断请求"""

    # CAS 6 五条件（True = 已满足）
    technical_feasibility: bool = Field(..., description="技术可行性已论证")
    completion_intent: bool = Field(..., description="具有完成并使用或出售的意图")
    ability_to_use_or_sell: bool = Field(..., description="使用或出售的能力")
    future_economic_benefits: bool = Field(..., description="产生未来经济利益的方式")
    resource_sufficiency: bool = Field(..., description="技术/财务/其他资源充足")

    # 各条件满足日期（仅对已满足条件要求；ISO 8601 YYYY-MM-DD）
    condition_dates: dict[str, str] = Field(
        default_factory=dict,
        description="各条件满足日期（仅对已满足条件提供）",
    )

    # 项目时间信息
    project_start_date: str = Field(..., description="研发项目启动日期（ISO 8601）")
    project_end_date: str | None = Field(
        None, description="研发项目预计完成日期（ISO 8601，可选）"
    )

    # 写回
    apply_to_sheet: str | None = Field(
        None,
        description="若给出 sheet 名，则将结果写回 working_paper.parsed_data.capitalization_checks[sheet]",
    )


class CapitalizationCheckResponse(BaseModel):
    """开发支出资本化时点判断响应"""

    all_conditions_met: bool
    capitalization_start_date: str | None
    missing_conditions: list[str]
    condition_status: dict[str, bool]
    recommendation: str
    applied_to_sheet: str | None = None


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _parse_iso_date(value: str, field_name: str) -> date:
    """解析 ISO 日期，失败抛 HTTP 422"""
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"{field_name} 格式无效（应为 YYYY-MM-DD），收到：{value!r}",
        ) from exc


def _evaluate_conditions(
    payload: CapitalizationCheckRequest,
) -> tuple[dict[str, bool], list[str]]:
    """构造条件状态字典 + 缺失条件名称列表"""
    status = {field: bool(getattr(payload, field)) for field in CONDITION_FIELDS}
    missing = [CONDITION_LABELS[f] for f, ok in status.items() if not ok]
    return status, missing


def _resolve_capitalization_start_date(
    payload: CapitalizationCheckRequest,
    status: dict[str, bool],
    project_start: date,
) -> date:
    """计算资本化起始日期 = max(已满足条件日期, 项目启动日期)

    规则：
    - 仅对已满足的条件要求 condition_dates 中提供日期
    - 起始日期 = max(全部已满足条件日期)
    - 不得早于项目启动日期（取较晚者）
    - 任一已满足条件未提供日期 → 422
    """
    dates: list[date] = []
    for field, ok in status.items():
        if not ok:
            continue
        raw = payload.condition_dates.get(field)
        if not raw:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"已满足条件 '{field}' 缺少满足日期；"
                    f"请在 condition_dates 中提供 {field}: 'YYYY-MM-DD'"
                ),
            )
        dates.append(_parse_iso_date(raw, f"condition_dates.{field}"))

    if not dates:  # 防御：不应到达（5 全 True 才会调用此函数）
        return project_start

    last_condition_date = max(dates)
    return max(last_condition_date, project_start)


# ─── Main Endpoint ────────────────────────────────────────────────────────────


@router.post("/capitalization-check", response_model=CapitalizationCheckResponse)
async def i2_capitalization_check(
    project_id: str,
    wp_id: str,
    payload: CapitalizationCheckRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_project_access("edit")),
) -> CapitalizationCheckResponse:
    """I-F5 开发支出资本化时点判断（CAS 6 五条件）

    - 全 True → 建议起始日期 = max(各条件满足日期, 项目启动日期)
    - 任一 False → 返回缺失条件清单
    """
    try:
        UUID(project_id)
    except Exception as exc:
        raise HTTPException(400, "invalid project_id") from exc

    # 项目日期解析
    project_start = _parse_iso_date(payload.project_start_date, "project_start_date")
    project_end: date | None = None
    if payload.project_end_date:
        project_end = _parse_iso_date(payload.project_end_date, "project_end_date")
        if project_end < project_start:
            raise HTTPException(
                status_code=400,
                detail="project_end_date 不能早于 project_start_date",
            )

    # 评估 5 条件
    condition_status, missing = _evaluate_conditions(payload)
    all_met = len(missing) == 0

    capitalization_start_date_iso: str | None = None
    if all_met:
        cap_start = _resolve_capitalization_start_date(payload, condition_status, project_start)
        # 资本化起始日期不得晚于项目预计完成日期
        if project_end is not None and cap_start > project_end:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"测算的资本化起始日期 {cap_start.isoformat()} "
                    f"晚于项目预计完成日期 {project_end.isoformat()}，请核对条件日期"
                ),
            )
        capitalization_start_date_iso = cap_start.isoformat()
        recommendation = (
            f"5 项条件全部满足，建议自 {capitalization_start_date_iso} 起将开发阶段支出资本化"
        )
    else:
        recommendation = (
            f"不满足资本化条件，缺失 {len(missing)} 项："
            + "；".join(missing)
            + "。在缺失条件满足前发生的支出应费用化（计入研发费用 I6）"
        )

    # 写回
    applied_to_sheet = await _maybe_apply_capitalization_check_to_workpaper(
        db,
        wp_id,
        payload,
        all_met=all_met,
        capitalization_start_date=capitalization_start_date_iso,
        missing_conditions=missing,
        condition_status=condition_status,
        recommendation=recommendation,
    )

    return CapitalizationCheckResponse(
        all_conditions_met=all_met,
        capitalization_start_date=capitalization_start_date_iso,
        missing_conditions=missing,
        condition_status=condition_status,
        recommendation=recommendation,
        applied_to_sheet=applied_to_sheet,
    )


# ─── Write-back Helper ────────────────────────────────────────────────────────


async def _maybe_apply_capitalization_check_to_workpaper(
    db: AsyncSession,
    wp_id: str,
    payload: CapitalizationCheckRequest,
    *,
    all_met: bool,
    capitalization_start_date: str | None,
    missing_conditions: list[str],
    condition_status: dict[str, bool],
    recommendation: str,
) -> str | None:
    """若 apply_to_sheet 给出则把判断结果写回 working_paper.parsed_data。

    数据结构：
      parsed_data.capitalization_checks[sheet] = {
        "all_conditions_met": bool,
        "capitalization_start_date": "YYYY-MM-DD" | null,
        "missing_conditions": [...],
        "condition_status": {<field>: bool, ...},
        "condition_dates": {<field>: "YYYY-MM-DD", ...},
        "project_start_date": "YYYY-MM-DD",
        "project_end_date": "YYYY-MM-DD" | null,
        "recommendation": "...",
        "applied_at": ISO8601,
      }
    """
    if not payload.apply_to_sheet:
        return None

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
    pd.setdefault("capitalization_checks", {})
    pd["capitalization_checks"][payload.apply_to_sheet] = {
        "all_conditions_met": all_met,
        "capitalization_start_date": capitalization_start_date,
        "missing_conditions": missing_conditions,
        "condition_status": condition_status,
        "condition_dates": dict(payload.condition_dates),
        "project_start_date": payload.project_start_date,
        "project_end_date": payload.project_end_date,
        "recommendation": recommendation,
        "applied_at": datetime.now(timezone.utc).isoformat(),
    }
    wp.parsed_data = pd
    await db.flush()
    await db.commit()
    return payload.apply_to_sheet
