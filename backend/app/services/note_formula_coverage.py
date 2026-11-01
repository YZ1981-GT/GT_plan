"""附注公式覆盖率统计，从执行器大文件拆出（S5 收口）。"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import DisclosureNote


def compute_formula_coverage(table_data: dict | None) -> dict[str, Any]:
    """有预设公式的金额格 / 全部金额格，口径与执行器完全相同。"""
    from app.services.note_formula_tables import (
        amount_columns, formula_view, iter_note_tables, parse_formula_key,
        section_preset_formulas,
    )

    if not table_data or not isinstance(table_data, dict):
        return {"total_cells": 0, "configured_cells": 0, "coverage_pct": 0.0}
    view = formula_view(table_data)
    formulas, _notes = section_preset_formulas(view)
    targets = {parsed for key in formulas if (parsed := parse_formula_key(key))}
    total_cells = configured_cells = 0
    for table_index, table in iter_note_tables(view):
        rows = table.get("rows") if isinstance(table.get("rows"), list) else []
        columns = set(amount_columns(table)) if table.get("headers") and rows else set()
        total_cells += len(rows) * len(columns)
        configured_cells += sum(
            1 for t, row, col in targets
            if t == table_index and row < len(rows) and col in columns
        )
    percentage = round(configured_cells * 100 / total_cells, 1) if total_cells else 0.0
    return {
        "total_cells": total_cells,
        "configured_cells": configured_cells,
        "coverage_pct": percentage,
    }


async def compute_project_formula_coverage(
    db: AsyncSession, project_id: UUID, year: int,
) -> dict[str, Any]:
    """聚合项目年度全部未删除附注章节的公式覆盖率。"""
    notes = list((await db.execute(sa.select(DisclosureNote).where(
        DisclosureNote.project_id == project_id,
        DisclosureNote.year == year,
        DisclosureNote.is_deleted == sa.false(),
    ))).scalars().all())
    total = configured = 0
    by_section: list[dict[str, Any]] = []
    for note in notes:
        if not note.table_data:
            continue
        stats = compute_formula_coverage(note.table_data)
        total += stats["total_cells"]
        configured += stats["configured_cells"]
        by_section.append({"note_section": note.note_section, **stats})
    return {
        "total_cells": total,
        "configured_cells": configured,
        "coverage_pct": round(configured * 100 / total, 1) if total else 0.0,
        "by_section": by_section,
    }
