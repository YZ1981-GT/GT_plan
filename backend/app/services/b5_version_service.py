"""B5 业务约定书版本推荐 — 读取 b5_version_matrix.json.

按 business_category 和项目特征自动推荐适用的约定书版本（B5-1~B5-9）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

_MATRIX_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "b5_version_matrix.json"


def _load_matrix() -> dict:
    return json.loads(_MATRIX_PATH.read_text(encoding="utf-8"))


async def _get_business_category(db: AsyncSession, project_id) -> str | None:
    r = await db.execute(
        sa.text("SELECT business_category FROM projects WHERE id = :pid"),
        {"pid": str(project_id)},
    )
    return r.scalar_one_or_none()


async def _get_project_signals(db: AsyncSession, project_id) -> set[str]:
    """从项目属性推断 signals（国企/医院/整合审计等）。"""
    signals: set[str] = set()
    try:
        r = await db.execute(
            sa.text(
                "SELECT audit_type, client_name FROM projects WHERE id = :pid"
            ),
            {"pid": str(project_id)},
        )
        row = r.mappings().first()
        if row:
            audit_type = row.get("audit_type") or ""
            if "integrated" in audit_type.lower() or "内控" in audit_type:
                signals.add("integrated_audit")
            client_name = row.get("client_name") or ""
            if any(k in client_name for k in ("医院", "卫生院", "诊所")):
                signals.add("hospital_audit")
    except Exception:
        pass
    return signals


async def recommend_b5_version(db: AsyncSession, project_id) -> dict[str, Any]:
    """推荐 B5 约定书主版本。"""
    matrix = _load_matrix()
    bc = await _get_business_category(db, project_id) or ""
    signals = await _get_project_signals(db, project_id)

    fallback = None
    matched = None
    for mv in matrix.get("main_versions", []):
        m = mv.get("match", {})
        cats = m.get("business_category", [])
        if cats and bc in cats:
            matched = mv
            break
        sig_list = m.get("signals", [])
        if sig_list and any(s in signals for s in sig_list):
            matched = mv
            break
        if m.get("default"):
            fallback = mv

    if not matched:
        matched = fallback or matrix["main_versions"][-1]

    confidence = matched.get("confidence", "high")
    reason = f"business_category={bc or '默认'}"
    if signals:
        reason += f"; signals={','.join(sorted(signals))}"

    return {
        "code": matched["code"],
        "label": matched["label"],
        "reason": reason,
        "confidence": confidence,
    }
