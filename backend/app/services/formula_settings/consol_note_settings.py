"""合并附注域：填数读有效公式 + 旧端点收口（design §12 consol_note，tasks 6.3）。

* 全局层 = ``consol_note_formula``（模板级表，按模板类型，带版本）；本项目层 = ``formula_setting``。
* 填数（``note_breakdown``）：全局公式被本项目适配覆盖，本项目停用的单元格剔除；读本项目层失败按全局（保存点隔离）。
* 旧端点 ``/api/consol-note-formulas`` 的增删改 = 全局发布：版本 +1，改过该单元格的项目按同步内核处理
  （跟随的自动更新、冲突生成待确认）；修改 / 删除须带版本号（缺 428、不符 409）。
* 自动种子（``seed_note_formulas``）是派生配置更新，只升版本、不经内核：本项目改过的单元格保留本项目公式。
只 flush；路由 commit 后发变更事件。
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.formula_settings.definitions import is_disabled
from app.services.formula_settings.domain_stores import consol_slot, split_consol_slot
from app.services.formula_settings.errors import FormulaSettingError
from app.services.formula_settings.publish import publish_global

logger = logging.getLogger(__name__)
DOMAIN = "consol_note"


@dataclass(frozen=True)
class NoteCellFormula:
    """本项目适配的单元格公式（形状同 ``ConsolNoteFormula`` 求值用到的字段）。"""

    row_index: int
    col_index: int
    formula: str
    source: str = "project"
    description: str | None = None


async def effective_formulas(db: AsyncSession, project_id: uuid.UUID, section_id: str,
                             global_rows: Sequence[Any]) -> list[Any]:
    """某章节的有效单元格公式（按行、列排序）。"""
    from app.models.formula_setting_models import FormulaSetting

    try:
        async with db.begin_nested():
            rows = (await db.execute(sa.select(FormulaSetting).where(
                FormulaSetting.domain == DOMAIN, FormulaSetting.layer == "project",
                FormulaSetting.project_id == project_id, FormulaSetting.is_deleted == sa.false(),
                FormulaSetting.slot_key.startswith(f"{section_id}|", autoescape=True)))).scalars().all()
    except Exception as exc:  # noqa: BLE001 —— 填数照全局继续
        logger.warning("合并附注本项目公式读取失败，按全局填数 project=%s: %s", project_id, exc)
        return list(global_rows)
    if not rows:
        return list(global_rows)
    cells: dict[tuple[int, int], Any] = {(f.row_index, f.col_index): f for f in global_rows}
    for r in rows:
        try:
            _, ri, ci = split_consol_slot(r.slot_key)
        except FormulaSettingError:
            continue
        d = r.definition or {}
        text = str(d.get("formula") or "").strip()
        if is_disabled(d) or not text:
            cells.pop((ri, ci), None)
        else:
            cells[(ri, ci)] = NoteCellFormula(ri, ci, text, "project", d.get("description"))
    return [cells[k] for k in sorted(cells)]


# ── 旧端点收口 ────────────────────────────────────────────────────────────────


async def _live(db: AsyncSession, template_type: str, section_id: str, row_index: int, col_index: int):
    from app.models.consol_push_models import ConsolNoteFormula

    return (await db.execute(sa.select(ConsolNoteFormula).where(
        ConsolNoteFormula.template_type == template_type, ConsolNoteFormula.section_id == section_id,
        ConsolNoteFormula.row_index == row_index, ConsolNoteFormula.col_index == col_index,
        ConsolNoteFormula.is_deleted == sa.false()))).scalars().first()


async def _publish(db: AsyncSession, row: Any, definition: dict | None, expected_version: int | None,
                   user_id: uuid.UUID | None) -> list[dict]:
    slot = consol_slot(row.section_id, row.row_index, row.col_index)
    result = await publish_global(db, domain=DOMAIN, scope=row.template_type, user_id=user_id, source="direct_edit",
                                  changes=[{"slot_key": slot, "definition": definition,
                                            "expected_version": expected_version}])
    return result.get("events") or []


async def create_formula(db: AsyncSession, *, template_type: str, section_id: str, row_index: int, col_index: int,
                         formula: str, description: str | None, user_id: uuid.UUID | None) -> tuple[Any, list[dict]]:
    from app.services.consol_note_formula_service import (
        NoteFormulaError,
        _check_cell,
        _check_template,
        validate_note_formula,
    )

    tt = _check_template(template_type)
    _check_cell(tt, section_id, row_index, col_index)
    text = validate_note_formula(formula)
    if await _live(db, tt, section_id, row_index, col_index) is not None:
        raise NoteFormulaError("该单元格已有公式，请直接修改", status=409)
    slot = consol_slot(section_id, row_index, col_index)
    result = await publish_global(db, domain=DOMAIN, scope=tt, user_id=user_id, source="direct_edit", changes=[{
        "slot_key": slot, "definition": {"formula": text, "description": (description or "").strip() or None}}])
    row = await _live(db, tt, section_id, row_index, col_index)
    if row is None:
        raise NoteFormulaError("新增合并附注公式失败", status=500)
    return row, result.get("events") or []


async def update_formula(db: AsyncSession, formula_id: uuid.UUID, *, formula: str | None, description: str | None,
                         expected_version: int | None, user_id: uuid.UUID | None) -> tuple[Any, list[dict]]:
    """改公式 ⇒ 来源变为人工；只差空白不算改；只改说明不改来源。"""
    from app.services.consol_note_formula_service import _get_formula, canonical_formula, validate_note_formula

    row = await _get_formula(db, formula_id)
    patch: dict[str, Any] = {}
    if formula is not None:
        text = validate_note_formula(formula)
        if canonical_formula(text) != canonical_formula(row.formula):
            patch["formula"] = text
    if description is not None and (description.strip() or None) != row.description:
        patch["description"] = description.strip() or None
    if not patch:
        return row, []
    return row, await _publish(db, row, patch, expected_version, user_id)


async def delete_formula(db: AsyncSession, formula_id: uuid.UUID, *, expected_version: int | None,
                         user_id: uuid.UUID | None) -> tuple[Any, list[dict]]:
    """软删（保留记录 ⇒ 种子不再补回该单元格）。"""
    from app.services.consol_note_formula_service import _get_formula

    row = await _get_formula(db, formula_id)
    return row, await _publish(db, row, None, expected_version, user_id)
