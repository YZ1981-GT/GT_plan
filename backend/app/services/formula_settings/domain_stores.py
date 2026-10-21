"""底稿 / 合并附注两个域的存储适配（design §12）。

* 底稿（wp）：全局层 = ``formula_setting``；系统预设 = ``prefill_formula_mapping.json``；
  本项目层 = ``wp_formula``（该项目该底稿编码的底稿；用户在底稿公式编辑器里存的行、
  以及同步内核写入的跟随 / 暂缓行）。公式位 ``{wp_code}|{sheet}|{cell}``。
  底稿域没有「停用」：停用定义不写（预填照常按上游）；项目还没有该底稿时，本项目层无处可写（跳过）。
  内核写本项目行不经 ``wp_formula_service.save``：那里按项目逐条校验引用是否存在（用户编辑的守卫），
  全局发布若因某个项目缺科目而整批失败，与「无本项目行的项目直接按全局取数、不做校验」也不一致；
  这里只拦结构损坏与危险内容（全局编辑时同一口径）。
* 合并附注（consol_note）：全局层 = ``consol_note_formula``（模板级表，按模板类型，带版本）；
  本项目层 = ``formula_setting``。公式位 ``{section_id}|{row}|{col}``。
"""
from __future__ import annotations

import dataclasses
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.formula_settings.definitions import is_disabled, same_exec
from app.services.formula_settings.errors import FormulaSettingError
from app.services.formula_settings.stores import SettingStore, SlotRecord

logger = logging.getLogger(__name__)
_MAPPING_PATH = Path(__file__).resolve().parents[3] / "data" / "prefill_formula_mapping.json"
_mapping_cache: dict[str, Any] = {"mtime": None, "records": {}}
#: 本项目层 = 用户在底稿上存过的公式行（三种来源都算本项目的定义）
WP_SOURCES = ("custom", "preset", "reference")
#: 预填引擎认的取数函数（部分不在公式引擎注册表里，如 TB_SUM / LEDGER / PLACEHOLDER，预设本身就在用）
PREFILL_FUNCTIONS = frozenset({"TB", "TB_SUM", "SUM_TB", "ADJ", "PREV", "WP", "AUX", "TB_AUX", "LEDGER",
                               "LEDGER_DETAIL", "COUNT_LEDGER", "NOTE", "PLACEHOLDER"})
WP_FORMULA_TYPES = ("auto_calc", "logic_check", "reasonability")


def checked_wp_definition(definition: dict, label: str) -> tuple[str, str]:
    """底稿公式定义的写入前检查：返回（去掉前导「=」的表达式, 公式类型）。"""
    from app.services.formula_engine import _REGISTRY
    from app.services.formula_management.formula_state import FormulaState, classify_formula

    expression = str(definition.get("expression") or "").strip().lstrip("=").strip()
    if not expression:
        raise FormulaSettingError(f"{label}：公式不能为空")
    ftype = str(definition.get("formula_type") or "auto_calc").strip()
    if ftype not in WP_FORMULA_TYPES:
        raise FormulaSettingError(f"{label}：公式类型须为 {' / '.join(WP_FORMULA_TYPES)}")
    known = set(_REGISTRY.known_function_names()) | PREFILL_FUNCTIONS
    state = classify_formula(expression, known_functions=known)
    if state is FormulaState.DAMAGED:
        raise FormulaSettingError(f"{label}：公式结构无法解析")
    if state is FormulaState.BLOCKED:
        raise FormulaSettingError(f"{label}：公式含不支持的函数、外链或危险内容")
    return expression, ftype


def wp_slot(wp_code: str, sheet: str, cell: str) -> str:
    return f"{wp_code}|{sheet}|{cell}"


def split_wp_slot(slot: str) -> tuple[str, str, str]:
    parts = slot.split("|", 2)
    if len(parts) != 3 or not parts[0] or not parts[2]:
        raise FormulaSettingError(f"底稿公式位格式应为「底稿编码|sheet|单元格」：{slot}")
    return parts[0], parts[1], parts[2]


def _mapping_records() -> dict[str, SlotRecord]:
    try:
        mtime = _MAPPING_PATH.stat().st_mtime
    except OSError:
        return {}
    if _mapping_cache["mtime"] == mtime:
        return _mapping_cache["records"]
    try:
        data = json.loads(_MAPPING_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("prefill_formula_mapping.json 读取失败：%s", exc)
        return {}
    records: dict[str, SlotRecord] = {}
    for m in data.get("mappings") or []:
        code, sheet = (m.get("wp_code") or "").strip(), (m.get("sheet") or "").strip()
        for cell in m.get("cells") or []:
            ref, formula = (cell.get("cell_ref") or "").strip(), cell.get("formula") or ""
            if not code or not ref or not formula or ref.startswith("_"):
                continue  # 「_」开头是汇总驱动占位格，不是可编辑单元格
            slot = wp_slot(code, sheet, ref)
            records[slot] = SlotRecord(slot_key=slot, definition={
                "expression": formula, "formula_type": "auto_calc",
                "description": cell.get("description") or "", "category": cell.get("formula_type") or ""},
                version=0, label=f"{code} {sheet}!{ref}".strip(), layer="preset")
    _mapping_cache.update(mtime=mtime, records=records)
    return records


class WpStore(SettingStore):
    def __init__(self) -> None:
        super().__init__("wp")

    async def system_presets(self, db, scope):
        return {k: dataclasses.replace(v, definition=dict(v.definition or {})) for k, v in _mapping_records().items()}

    async def write_global(self, db, scope, slot_key, definition, *, user_id, label="", structure=None):
        split_wp_slot(slot_key)
        if definition is not None:
            checked_wp_definition(definition, label or slot_key)
        return await super().write_global(db, scope, slot_key, definition, user_id=user_id, label=label,
                                          structure=structure)

    async def _rows(self, db: AsyncSession, project_ids: list[uuid.UUID]):
        from app.models.workpaper_models import WorkingPaper, WpFormula, WpIndex

        q = (sa.select(WpFormula, WpIndex.wp_code)
             .join(WorkingPaper, WorkingPaper.id == WpFormula.wp_id)
             .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
             .where(WpFormula.project_id.in_(project_ids), WpFormula.formula_source.in_(WP_SOURCES),
                    WorkingPaper.is_deleted == sa.false())
             .order_by(WpFormula.created_at, WpFormula.id))
        return (await db.execute(q)).all()

    @staticmethod
    def _record(row, wp_code: str) -> SlotRecord:
        slot = wp_slot(wp_code, row.sheet_name, row.target_cell)
        return SlotRecord(
            slot_key=slot, label=f"{wp_code} {row.sheet_name}!{row.target_cell}",
            definition={"expression": row.expression, "formula_type": row.formula_type,
                        "description": row.description, "category": row.category},
            version=row.definition_version or 1, base_definition=row.base_definition, base_version=row.base_version,
            pinned=bool(row.pinned), base_origin=row.base_origin, base_template_id=row.base_template_id,
            row_id=row.id, layer="project")

    async def list_project(self, db, project_id):
        return (await self.list_project_many(db, [project_id]))[project_id]

    async def list_project_many(self, db, project_ids):
        out: dict[uuid.UUID, dict[str, SlotRecord]] = {pid: {} for pid in project_ids}
        if not project_ids:
            return out
        # 同一项目同编码有多张底稿时取最早建的那行（写入时各张底稿同步写，正常情况下一致）
        for row, code in await self._rows(db, list(project_ids)):
            out[row.project_id].setdefault(wp_slot(code, row.sheet_name, row.target_cell), self._record(row, code))
        return out

    async def _project_wps(self, db: AsyncSession, project_id: uuid.UUID, wp_code: str) -> list[uuid.UUID]:
        from app.models.workpaper_models import WorkingPaper, WpIndex

        return list((await db.execute(sa.select(WorkingPaper.id).join(
            WpIndex, WpIndex.id == WorkingPaper.wp_index_id).where(
            WorkingPaper.project_id == project_id, WpIndex.wp_code == wp_code,
            WorkingPaper.is_deleted == sa.false()))).scalars().all())

    async def _cell_rows(self, db: AsyncSession, wp_ids: list[uuid.UUID], sheet: str, cell: str):
        from app.models.workpaper_models import WpFormula

        return list((await db.execute(sa.select(WpFormula).where(
            WpFormula.wp_id.in_(wp_ids), WpFormula.sheet_name == sheet, WpFormula.target_cell == cell,
        ))).scalars().all())

    async def write_project(self, db, project_id, slot_key, *, definition, base_definition, base_version,
                            pinned, base_origin, base_template_id, user_id, label="", structure=None):
        if is_disabled(definition):
            logger.info("底稿域无停用：跳过写入 project=%s slot=%s", project_id, slot_key)
            return
        from app.models.workpaper_models import WpFormula
        from app.services.formula_management.stable_key import derive_stable_key
        from app.services.wp_formula_service import _compute_definition_hash

        code, sheet, cell = split_wp_slot(slot_key)
        wp_ids = await self._project_wps(db, project_id, code)
        if not wp_ids:
            # 本项目还没有该底稿 ⇒ 没有可适配的对象（建底稿时按上游预填）。
            # 暂缓 / 冻结写入的固定行也到不了（R4.3），记可见降级以便排查。
            if pinned:
                logger.warning("底稿域：项目 %s 无底稿 %s，暂缓固定行无处落地（建底稿后将按新全局预填）", project_id, code)
            return
        expression, ftype = checked_wp_definition(definition, label or slot_key)
        follow = base_definition is not None and same_exec("wp", definition, base_definition)
        stable = derive_stable_key(sheet, cell)
        existing = {r.wp_id: r for r in await self._cell_rows(db, wp_ids, sheet, cell)}
        now = datetime.now(timezone.utc)
        for wp_id in wp_ids:
            row = existing.get(wp_id)
            if row is None:
                row = WpFormula(id=uuid.uuid4(), project_id=project_id, wp_id=wp_id, sheet_name=sheet,
                                target_cell=cell, refs=[], created_by=user_id, created_at=now, definition_version=0)
                db.add(row)
            elif row.expression != expression:
                row.refs = []  # 旧引用清单按旧表达式解析，表达式变了不再适用
            row.expression, row.formula_type = expression, ftype
            row.category = definition.get("category") or None
            row.description = definition.get("description") or None
            row.formula_source = "preset" if follow else "custom"
            row.reference_formula_id = None
            row.stable_sheet_key, row.row_key, row.field_key = stable.stable_sheet_key, stable.row_key, stable.field_key
            row.stable_key_needs_review = stable.needs_review
            row.definition_hash = _compute_definition_hash(expression, ftype, row.refs or [], row.source_scope,
                                                           row.binding)
            row.definition_version = (row.definition_version or 0) + 1
            row.lifecycle_state, row.updated_at = "saved", now
            row.base_definition = dict(base_definition) if base_definition is not None else None
            row.base_version, row.pinned = base_version, bool(pinned)
            row.base_origin, row.base_template_id = base_origin, base_template_id
        await db.flush()

    async def delete_project(self, db, project_id, slot_key):
        from app.services.wp_formula_service import wp_formula_service

        code, sheet, cell = split_wp_slot(slot_key)
        wp_ids = await self._project_wps(db, project_id, code)
        rows = [r for r in await self._cell_rows(db, wp_ids, sheet, cell) if r.formula_source in WP_SOURCES] \
            if wp_ids else []
        for row in rows:
            try:  # 参照它的公式标失效；失败不阻断（保存点隔离，PG 事务不进 aborted）
                async with db.begin_nested():
                    await wp_formula_service._invalidate_reference_dependents(
                        db, source_formula_id=row.id, project_id=project_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("底稿公式参照失效失败（不阻断）row=%s: %s", row.id, exc)
            await db.delete(row)
        if rows:
            await db.flush()


def validate_definition(domain: str, definition: dict, label: str) -> None:
    """模板 / 手工录入的定义按域校验（与各域写入时同一口径）；停用不能写进模板。"""
    if is_disabled(definition):
        raise FormulaSettingError(f"{label}：模板里只放公式，不能放「停用」")
    if domain == "wp":
        checked_wp_definition(definition, label)
    elif domain == "note":
        check_note_definition(definition, label)
    elif domain == "consol_note":
        from app.services.consol_note_formula_service import NoteFormulaError, validate_note_formula

        try:
            validate_note_formula(str(definition.get("formula") or ""))
        except NoteFormulaError as exc:
            raise FormulaSettingError(f"{label}：{exc}") from exc


# ── 附注 ──────────────────────────────────────────────────────────────────────

NOTE_CATEGORIES = ("auto_calc", "logic_check", "reasonability")


def check_note_definition(definition: dict | None, label: str) -> None:
    if definition is None or is_disabled(definition):
        return
    if not str(definition.get("formula") or "").strip():
        raise FormulaSettingError(f"{label}：公式不能为空")
    if (definition.get("category") or "auto_calc") not in NOTE_CATEGORIES:
        raise FormulaSettingError(f"{label}：公式类别须为 {' / '.join(NOTE_CATEGORIES)}")


class NoteStore(SettingStore):
    """附注：两层都在 ``formula_setting``（全局按模板类型）；公式位 ``{章节}|{目标单元格}``。"""

    def __init__(self) -> None:
        super().__init__("note")

    async def write_global(self, db, scope, slot_key, definition, *, user_id, label="", structure=None):
        check_note_definition(definition, label or slot_key)
        return await super().write_global(db, scope, slot_key, definition, user_id=user_id, label=label,
                                          structure=structure)

    async def write_project(self, db, project_id, slot_key, **kwargs):
        check_note_definition(kwargs.get("definition"), kwargs.get("label") or slot_key)
        await super().write_project(db, project_id, slot_key, **kwargs)


# ── 合并附注 ──────────────────────────────────────────────────────────────────


def consol_slot(section_id: str, row_index: int, col_index: int) -> str:
    return f"{section_id}|{row_index}|{col_index}"


def split_consol_slot(slot: str) -> tuple[str, int, int]:
    parts = slot.split("|")
    try:
        return parts[0], int(parts[1]), int(parts[2])
    except (IndexError, ValueError):
        raise FormulaSettingError(f"合并附注公式位格式应为「章节|行|列」：{slot}") from None


class ConsolNoteStore(SettingStore):
    supports_any_scope = False

    def __init__(self) -> None:
        super().__init__("consol_note")

    @staticmethod
    def _global_record(row) -> SlotRecord:
        slot = consol_slot(row.section_id, row.row_index, row.col_index)
        return SlotRecord(slot_key=slot, definition={"formula": row.formula, "description": row.description},
                          version=row.version or 1, label=f"{row.section_id} 第{row.row_index}行第{row.col_index}列",
                          row_id=row.id, layer="global")

    async def list_global(self, db, scope):
        from app.models.consol_push_models import ConsolNoteFormula

        rows = (await db.execute(sa.select(ConsolNoteFormula).where(
            ConsolNoteFormula.template_type == scope, ConsolNoteFormula.is_deleted == sa.false()))).scalars().all()
        return {r.slot_key: r for r in map(self._global_record, rows)}

    async def list_global_exact(self, db, scope):
        return await self.list_global(db, scope)

    async def write_project(self, db, project_id, slot_key, **kwargs):
        definition = kwargs.get("definition")
        split_consol_slot(slot_key)
        if definition and not is_disabled(definition):
            from app.services.consol_note_formula_service import NoteFormulaError, validate_note_formula

            try:
                validate_note_formula(str(definition.get("formula") or ""))
            except NoteFormulaError as exc:
                raise FormulaSettingError(f"{kwargs.get('label') or slot_key}：{exc}") from exc
        await super().write_project(db, project_id, slot_key, **kwargs)

    async def write_global(self, db, scope, slot_key, definition, *, user_id, label="", structure=None):
        from app.models.consol_push_models import ConsolNoteFormula
        from app.services.consol_note_formula_service import (
            NoteFormulaError,
            _check_cell,
            canonical_formula,
            validate_note_formula,
        )

        section, row_i, col_i = split_consol_slot(slot_key)
        try:
            if definition is not None:
                _check_cell(scope, section, row_i, col_i)
                text = validate_note_formula(str(definition.get("formula") or ""))
        except NoteFormulaError as exc:
            raise FormulaSettingError(f"{label or slot_key}：{exc}", status_code=exc.status) from exc
        rows = (await db.execute(sa.select(ConsolNoteFormula).where(
            ConsolNoteFormula.template_type == scope, ConsolNoteFormula.section_id == section,
            ConsolNoteFormula.row_index == row_i, ConsolNoteFormula.col_index == col_i))).scalars().all()
        live = next((r for r in rows if not r.is_deleted), None)
        now = datetime.now(timezone.utc)
        if definition is None:
            if live is None:
                return 0
            live.is_deleted, live.version, live.updated_by, live.updated_at = True, (live.version or 1) + 1, user_id, now
            return live.version
        description = (definition.get("description") or "").strip() or None
        if live is None:
            live = ConsolNoteFormula(template_type=scope, section_id=section, row_index=row_i, col_index=col_i,
                                     formula=text, source="manual", description=description, version=1,
                                     updated_by=user_id, created_at=now, updated_at=now)
            db.add(live)
            await db.flush()
            return 1
        if canonical_formula(text) != canonical_formula(live.formula):  # 只差空白不算改；只改说明不改来源
            live.formula, live.source = text, "manual"
        live.description = description
        live.version = (live.version or 1) + 1
        live.updated_by, live.updated_at = user_id, now
        return live.version
