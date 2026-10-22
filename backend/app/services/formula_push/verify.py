"""推送反向校验（spec: formula-management-deep-optimization · R5）。

对每个已推送的地址重新取源头值，对比目标当前值，分类差异：
- consistent: 源头值 == 目标值
- diverged: 数值不一致（标偏差额）
- manual_override: 目标被用户手工修改（state=manual/locked）
- stale: 源头已更新但未重新推送
"""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.formula_push_models import FormulaPushRun, FormulaPushState

logger = logging.getLogger(__name__)


def _to_decimal(val: Any) -> Decimal | None:
    """安全转换为 Decimal。"""
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _values_match(a: Any, b: Any, tolerance: Decimal = Decimal("0.005")) -> bool:
    """两值是否在容差内一致。"""
    da, db = _to_decimal(a), _to_decimal(b)
    if da is None and db is None:
        return True
    if da is None or db is None:
        return False
    return abs(da - db) < tolerance


async def verify_push(
    db: AsyncSession, project_id: uuid.UUID, year: int
) -> dict[str, Any]:
    """反向校验：对比源头值与目标当前值。"""
    states = (await db.execute(
        sa.select(FormulaPushState).where(
            FormulaPushState.project_id == project_id,
            FormulaPushState.year == year,
        )
    )).scalars().all()

    if not states:
        return {"total": 0, "items": [], "summary": {"consistent": 0, "diverged": 0, "manual_override": 0, "stale": 0}}

    # 查最近一次 run 获取时间戳
    last_run = (await db.execute(
        sa.select(FormulaPushRun).where(
            FormulaPushRun.project_id == project_id,
            FormulaPushRun.year == year,
        ).order_by(FormulaPushRun.started_at.desc()).limit(1)
    )).scalars().first()

    items: list[dict[str, Any]] = []
    counts = {"consistent": 0, "diverged": 0, "manual_override": 0, "stale": 0}

    for state in states:
        source_val = _to_decimal(state.last_formula_value)
        pushed_val = _to_decimal(state.last_pushed_value)
        current_val = _to_decimal(state.current_value)

        # 分类
        if state.state in ("manual", "locked"):
            status = "manual_override"
        elif pushed_val is None:
            status = "stale"  # 从未推送过
        elif source_val is not None and not _values_match(source_val, pushed_val):
            status = "stale"  # 源头已变但未重推
        elif current_val is not None and pushed_val is not None and not _values_match(current_val, pushed_val):
            status = "diverged"  # 推送后目标值变了
        else:
            status = "consistent"

        delta = None
        if status == "diverged" and current_val is not None and pushed_val is not None:
            delta = str(current_val - pushed_val)

        counts[status] = counts.get(status, 0) + 1
        items.append({
            "addr_id": state.addr_id,
            "domain": state.domain,
            "rule_id": state.rule_id,
            "status": status,
            "source_value": str(source_val) if source_val is not None else None,
            "pushed_value": str(pushed_val) if pushed_val is not None else None,
            "current_value": str(current_val) if current_val is not None else None,
            "delta": delta,
            "state": state.state,
            "updated_at": state.updated_at.isoformat() if state.updated_at else None,
        })

    return {
        "total": len(items),
        "last_run_at": last_run.started_at.isoformat() if last_run and last_run.started_at else None,
        "items": items,
        "summary": counts,
    }
