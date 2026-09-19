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

实现（三级回退，只读幂等不写库）
----
1. **用户公式**：扫 ``disclosure_notes.table_data._formulas``（顶层 dict）寻找
   expression 包含 ``REPORT('{row_code}', ...)`` 的章节；多表章节通过
   ``_formulas[key].table_index`` 区分（缺省 0）。origin=``formula``。
2. **写值 linkage**（回退）：经 ``ReportNoteLinkage.targets_for_report_row``
   扫内嵌 Cell_Binding（source=='report'）+ ``report_note_linkage.json`` 配置。
   origin=``linkage``。
3. **勾稽预设**（再回退）：预设库中 ``page_key == note:{章节}`` 且
   ``formula_type == 'logic_check'`` 且表达式引用本 row_code 的章节——
   报表↔附注按决策 1 **只校验不写值**，故"有勾稽关系"也是有效的可追溯关系。
   origin=``cross_check``。

同一 (note_section, table_index) 只出现一次，优先级 formula > linkage > cross_check。
任一级异常一律 fail-open（跳过该级，不阻断其余）。
"""

from __future__ import annotations

import logging
import re
from types import SimpleNamespace
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
    # 关系来源（additive，向后兼容旧前端）：
    # formula=附注内用户公式引用 / linkage=写值 linkage（Cell_Binding 或配置）
    # / cross_check=勾稽预设（只校验不写值）
    origin: str = "formula"


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


def find_cross_check_sections_for_row(row_code: str) -> set[str]:
    """从预设库找出「勾稽表达式引用 row_code」的附注章节集合（第 3 级回退）。

    报表↔附注按决策 1 **只校验不写值**，所以"存在 logic_check 勾稽"本身就是有效的
    可追溯关系（如 ``ABS(ROW('BS-002')-NOTE('五、1','合计'))<=1``）。

    预设库不可用 / 解析失败 → 返回空集（fail-open，不阻断其余两级）。
    """
    if not isinstance(row_code, str) or not row_code.strip():
        return set()
    try:
        from app.services.formula_management.preset_library import build_preset_library

        entries, _stats = build_preset_library()
    except Exception as err:  # pragma: no cover — 预设库不可用时安全降级
        logger.warning("preset library unavailable for row %s: %s", row_code, err)
        return set()

    pattern = re.compile(
        rf"""(?:REPORT|ROW)\(\s*['"]{re.escape(row_code)}['"]""",
        re.IGNORECASE,
    )
    out: set[str] = set()
    for e in entries:
        page_key = getattr(e, "page_key", "") or ""
        if not page_key.startswith("note:"):
            continue
        if getattr(e, "formula_type", "") != "logic_check":
            continue
        expr = getattr(e, "expression", "") or ""
        if isinstance(expr, str) and pattern.search(expr):
            section = page_key[len("note:") :].strip()
            if section:
                out.add(section)
    return out


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

    titles: dict[str, str] = {}
    matches: list[NoteReference] = []
    seen: set[tuple[str, int]] = set()

    def _add(section: str, tidx: int, origin: str) -> None:
        key = (section, tidx)
        if not section or key in seen:
            return
        seen.add(key)
        matches.append(
            NoteReference(
                note_section=section,
                section_title=titles.get(section, ""),
                table_index=tidx,
                origin=origin,
            )
        )

    # ── 第 1 级：附注内用户公式（_formulas）──────────────────────────────
    note_objs: list[SimpleNamespace] = []
    for row in rows:
        note_section = row[0] or ""
        section_title = row[1] or ""
        table_data = row[2]

        if not note_section:
            continue
        titles[note_section] = section_title
        if not isinstance(table_data, dict):
            continue
        note_objs.append(
            SimpleNamespace(note_section=note_section, table_data=table_data, id=None)
        )

        formulas = table_data.get("_formulas")
        for tidx in sorted(find_report_references_in_formulas(formulas, row_code)):
            _add(note_section, tidx, "formula")

    # ── 第 2 级：写值 linkage（Cell_Binding + 配置回退）──────────────────
    try:
        from app.services.report_note_linkage import ReportNoteLinkage

        for t in ReportNoteLinkage().targets_for_report_row(note_objs, row_code):
            _add(t.note_section, t.table_index, "linkage")
    except Exception as err:  # pragma: no cover — fail-open，不阻断其余级
        logger.warning("linkage lookup failed for row %s: %s", row_code, err)

    # ── 第 3 级：勾稽预设（只校验不写值，仍是有效可追溯关系）────────────
    try:
        for section in sorted(find_cross_check_sections_for_row(row_code)):
            # 仅呈现本项目实际存在的章节（预设库是全局的）
            if section in titles:
                _add(section, 0, "cross_check")
    except Exception as err:  # pragma: no cover — fail-open
        logger.warning("cross-check lookup failed for row %s: %s", row_code, err)

    matches.sort(key=lambda n: (n.note_section, n.table_index))
    return NoteReferencesResponse(row_code=row_code, notes=matches)
