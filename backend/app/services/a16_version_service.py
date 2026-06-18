"""A16 声明书版本推荐 — 读取 a16_version_matrix.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

_MATRIX_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "a16_version_matrix.json"


def _load_matrix() -> dict:
    return json.loads(_MATRIX_PATH.read_text(encoding="utf-8"))


async def _get_business_category(db: AsyncSession, project_id) -> str | None:
    r = await db.execute(
        sa.text("SELECT business_category FROM projects WHERE id = :pid"),
        {"pid": str(project_id)},
    )
    return r.scalar_one_or_none()


async def _integrated_audit_signal(db: AsyncSession, project_id) -> bool:
    r = await db.execute(
        sa.text(
            "SELECT 1 FROM procedure_instances pi "
            "JOIN working_papers wp ON wp.id = pi.working_paper_id "
            "WHERE wp.project_id = :pid AND wp.wp_code LIKE 'B60%' LIMIT 1"
        ),
        {"pid": str(project_id)},
    )
    return r.scalar_one_or_none() is not None


async def _related_party_count(db: AsyncSession, project_id) -> int:
    try:
        r = await db.execute(
            sa.text(
                "SELECT COUNT(*) FROM checklist_responses cr "
                "JOIN working_papers wp ON wp.id = cr.wp_id "
                "WHERE wp.project_id = :pid AND wp.wp_code = 'A7-1'"
            ),
            {"pid": str(project_id)},
        )
        return int(r.scalar_one() or 0)
    except Exception:
        return 0


async def recommend_main_version(db: AsyncSession, project_id) -> dict[str, Any]:
    matrix = _load_matrix()
    bc = await _get_business_category(db, project_id) or ""
    integrated = await _integrated_audit_signal(db, project_id)

    matched = None
    for mv in matrix.get("main_versions", []):
        m = mv.get("match", {})
        cats = m.get("business_category", [])
        if cats and bc in cats:
            matched = mv
            break
        if m.get("signals") == ["integrated_audit"] and integrated:
            matched = mv
            break
        if m.get("default"):
            fallback = mv

    if not matched:
        matched = fallback if "fallback" in dir() else matrix["main_versions"][-1]

    confidence = matched.get("confidence", "high")
    reason = f"business_category={bc or '默认'}"
    if integrated and matched.get("code") == "A16-2":
        reason += "; 整合审计信号"

    return {
        "code": matched["code"],
        "label": matched["label"],
        "reason": reason,
        "confidence": confidence,
    }


async def recommend_supplement(db: AsyncSession, project_id) -> dict[str, Any] | None:
    matrix = _load_matrix()
    sup = matrix.get("supplement")
    if not sup:
        return None
    count = await _related_party_count(db, project_id)
    if count > 0:
        return {"code": sup["code"], "label": sup["label"], "reason": f"关联交易行数={count}"}
    return None
