"""报表行 → 附注引用反向溯源 API（Sprint 4 Task 4.3 / R7-S4-12）.

Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 4 Task 4.3
Reqs:   报表 ReportView「附注引用我」侧栏 — rowCode → 反查所有引用此报表项
        的 note_section（双向溯源跳转）。

端点
----
GET /api/financial-reports/{project_id}/{year}/{row_code}/note-references

返回
----
{
    "row_code": "BS-001",
    "notes": [
        {
            "note_section": "五、1 货币资金",
            "section_title": "货币资金",
            "table_index": 0
        },
        ...
    ]
}

实现
----
1. 扫 ``disclosure_notes.table_data._formulas``（顶层 dict）寻找
   expression 包含 ``REPORT('{row_code}', ...)``  的章节。
2. 多表章节通过 ``_formulas[key].source`` 中的 table_index 区分（缺省 0）。
3. 只读端点，幂等，不写库。
"""

from __future__ import annotations

import logging
import re
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/financial-reports",
    tags=["report-note-references"],
)


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------


class NoteReference(BaseModel):
    note_section: str
    section_title: str = ""
    table_index: int = 0


class NoteReferencesResponse(BaseModel):
    row_code: str
    notes: list[NoteReference] = []


# ---------------------------------------------------------------------------
# 公式扫描 helper（纯函数，方便单测）
# ---------------------------------------------------------------------------


def find_report_references_in_formulas(
    formulas: dict[str, Any] | None,
    row_code: str,
) -> set[int]:
    """从 note.table_data._formulas dict 抽出引用 ``row_code`` 的 table_index 集合.

    ``_formulas`` schema (D4 沉淀位置)::

        {
            "0:1": {
                "expression": "=REPORT('BS-001','current')",
                "source": "check_presets.balance",
                "table_index": 0,    # 可选，多表章节
                ...
            },
            ...
        }

    Args:
        formulas: ``note.table_data.get('_formulas')`` 顶层 dict。
        row_code: 待匹配的报表行编码（如 ``"BS-001"``）。

    Returns:
        命中的 table_index 集合；缺 ``table_index`` 字段默认 0。
    """
    if not isinstance(formulas, dict) or not row_code:
        return set()

    # 精准匹配 REPORT('{row_code}', ...) — 单引号 / 双引号都允许
    # 同时兼容 ROW('{row_code}') 老语法
    pattern = re.compile(
        rf"""(?:REPORT|ROW)\(\s*['"]({re.escape(row_code)})['"]""",
        re.IGNORECASE,
    )
    hits: set[int] = set()
    for key, fdef in formulas.items():
        if not isinstance(fdef, dict):
            continue
        expr = fdef.get("expression") or fdef.get("formula") or ""
        if not isinstance(expr, str):
            continue
        if pattern.search(expr):
            tidx = fdef.get("table_index", 0)
            if not isinstance(tidx, int) or tidx < 0:
                tidx = 0
            hits.add(tidx)
    return hits


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/{project_id}/{year}/{row_code}/note-references",
    response_model=NoteReferencesResponse,
)
async def get_note_references_for_row(
    project_id: UUID,
    year: int,
    row_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """反查所有引用 ``row_code`` 的附注章节（双向溯源跳转）.

    返回的章节按 (note_section, table_index) 升序，便于前端稳定展示。
    """
    if not row_code or not row_code.strip():
        return NoteReferencesResponse(row_code=row_code, notes=[])

    try:
        result = await db.execute(
            sa.text(
                "SELECT note_section, section_title, table_data "
                "FROM disclosure_notes "
                "WHERE project_id = :pid AND year = :yr "
                "AND is_deleted = false "
                "AND table_data IS NOT NULL"
            ),
            {"pid": str(project_id), "yr": year},
        )
        rows = result.fetchall()
    except Exception as e:
        logger.warning("Failed to query disclosure_notes for row %s: %s", row_code, e)
        return NoteReferencesResponse(row_code=row_code, notes=[])

    matches: list[NoteReference] = []
    for row in rows:
        note_section = row[0] or ""
        section_title = row[1] or ""
        table_data = row[2]

        if not note_section or not isinstance(table_data, dict):
            continue

        formulas = table_data.get("_formulas")
        table_indexes = find_report_references_in_formulas(formulas, row_code)
        for tidx in sorted(table_indexes):
            matches.append(
                NoteReference(
                    note_section=note_section,
                    section_title=section_title,
                    table_index=tidx,
                )
            )

    matches.sort(key=lambda n: (n.note_section, n.table_index))
    return NoteReferencesResponse(row_code=row_code, notes=matches)
