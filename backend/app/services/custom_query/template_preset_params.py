"""系统预置参数的项目级取值（`template_presets` 的伴生模块）。"""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select

from app.models.core import Project
from app.services.materiality_service import MaterialityService
from app.services.sampling_enhanced_service import (
    DEFAULT_CUTOFF_DAYS_AFTER,
    DEFAULT_CUTOFF_DAYS_BEFORE,
    cutoff_window,
)

logger = logging.getLogger(__name__)
PARAM_LABELS = {
    "materiality_performance": "实际执行的重要性水平",
    "cutoff_start": "截止窗口起始日",
    "cutoff_end": "截止窗口结束日",
}


def _materiality_item(raw_value: Any, *, year: int, read_failed: bool) -> dict[str, Any]:
    raw: Decimal | None = None
    if not read_failed and raw_value is not None:
        try:
            raw = Decimal(str(raw_value))
        except (InvalidOperation, ValueError):
            read_failed = True

    valid = raw is not None and not read_failed and raw > 0
    if read_failed:
        missing = "重要性水平读取失败，请填写阈值"
    elif raw is None:
        missing = f"本项目 {year} 年度未设置重要性水平，请填写阈值"
    elif raw < 0:
        missing = f"本项目重要性水平为负数（{raw:,.2f}），不能作为阈值，请填写"
    else:
        missing = f"本项目重要性水平为 {raw:,.2f}，必须大于 0，请填写阈值"
    return {
        "key": "materiality_performance",
        "label": PARAM_LABELS["materiality_performance"],
        "value": str(raw) if valid else None,
        "basis": f"本项目 {year} 年度实际执行的重要性水平 {raw:,.2f} 元" if valid else None,
        "missing_reason": None if valid else missing,
    }


async def _materiality(db: Any, project_id: uuid.UUID, year: int) -> dict[str, Any]:
    raw = None
    failed = False
    try:
        async with db.begin_nested():
            current = await MaterialityService(db).get_current(project_id, year)
            raw = current.performance_materiality if current is not None else None
    except Exception as exc:  # noqa: BLE001 — 参数缺失可由用户填写，不能打断预置列表
        failed = True
        logger.warning("重要性水平读取失败 project_id=%s year=%s：%s", project_id, year, exc)
    return _materiality_item(raw, year=year, read_failed=failed)


async def _cutoff(db: Any, project_id: uuid.UUID, year: int) -> dict[str, dict[str, Any]]:
    cutoff_date = None
    try:
        async with db.begin_nested():
            result = await db.execute(
                select(Project.audit_period_end).where(Project.id == project_id).limit(1)
            )
            candidate = result.scalar_one_or_none()
        if candidate is not None and candidate.year == year:
            cutoff_date = candidate
    except Exception as exc:  # noqa: BLE001 — 与截止测试相同，读不到项目日期时按年度末
        logger.warning("项目截止日读取失败，按年度末计算 project_id=%s year=%s：%s", project_id, year, exc)

    window = cutoff_window(year, cutoff_date=cutoff_date)
    basis = (
        f"期末日 {window.period_end.isoformat()} 前 {DEFAULT_CUTOFF_DAYS_BEFORE} 天、"
        f"后 {DEFAULT_CUTOFF_DAYS_AFTER} 天（与截止性测试同一默认值）"
    )
    return {
        key: {
            "key": key,
            "label": PARAM_LABELS[key],
            "value": value.isoformat(),
            "basis": basis,
            "missing_reason": None,
        }
        for key, value in (("cutoff_start", window.start), ("cutoff_end", window.end))
    }


async def resolve_parameter_values(
    db: Any, project_id: Any, year: int, names: list[str]
) -> dict[str, dict[str, Any]]:
    """按出现顺序所需的参数名，读取本项目本年度取值。"""
    project_uuid = uuid.UUID(str(project_id))
    values: dict[str, dict[str, Any]] = {}
    if "materiality_performance" in names:
        values["materiality_performance"] = await _materiality(db, project_uuid, year)
    if {"cutoff_start", "cutoff_end"} & set(names):
        values.update(await _cutoff(db, project_uuid, year))
    return values
