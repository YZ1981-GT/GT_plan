"""附注-底稿映射与提数服务

Phase 9 Task 9.21: 附注从底稿提数 + 手动编辑锁定
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Iterator
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.report_models import DisclosureNote
from app.services.note_edit_stamp import stamp_note_edit

logger = logging.getLogger(__name__)

# ─── 附注章节 → 底稿编号映射 ────────────────────────────────────────────────
# 权威真源：backend/data/note_workpaper_sync_registry.json（由
# scripts/gen_note_wp_sync_registry.py 从前端 *NoteSectionMap.ts 生成）。
# 早期硬编码 DEFAULT_WP_MAPPING 的编号与 wp_code 双重错乱（如 "五、2"→"E2"[不存在]、
# "五、3"→"D1"[应收账款实为 D2/五、5]、"五、9"→"H1"[固定资产实为 五、22]），
# 被 note_validation_executors（完整性）/ note_stale_service（stale 标记）/
# disclosure_notes（schema 反查）三处直接消费 → 校验/标记/取数按错误映射进行。
# 现改为从 registry 派生 section→wp_code（listed + soe 双编号，权威），
# registry 不可用时 fail-open 回退旧值（保 import 不崩，极端情况行为=改动前）。

# 旧硬编码（错乱，仅作 registry 不可用时的 fail-open 回退，勿再据此判断）
_LEGACY_DEFAULT_WP_MAPPING = {
    "五、1": "E1",
    "五、2": "E2",
    "五、3": "D1",
    "五、6": "F1",
    "五、7": "G1",
    "五、9": "H1",
    "五、12": "I1",
    "五、16": "L1",
    "五、19": "J1",
    "五、29": "D1",
}


def _build_default_wp_mapping() -> dict[str, str]:
    """从权威 registry 派生 ``note_section → wp_code``（listed+soe 双编号，首个赢）。

    与 note_readiness_service.section_workpaper_map 同源（同一 JSON），此处产出
    单值形态（section→wp_code）供 stale/completeness/schema 三处消费者直接使用。
    读取失败 → fail-open 回退 _LEGACY_DEFAULT_WP_MAPPING（保底不崩）。
    """
    try:
        import json
        from pathlib import Path

        p = (
            Path(__file__).resolve().parent.parent.parent
            / "data"
            / "note_workpaper_sync_registry.json"
        )
        raw = json.loads(p.read_text(encoding="utf-8"))
        from app.services.note_readiness_service import registry_sections

        out: dict[str, str] = {}
        for e in raw.get("entries", []):
            if not isinstance(e, dict):
                continue
            code = str(e.get("wp_code") or "").strip()
            if not code:
                continue
            for variant in ("listed", "soe"):
                for sec in registry_sections(e, variant):
                    out.setdefault(sec, code)  # 首个赢，避免一 section 多 wp 覆盖
        if out:
            return out
    except Exception:  # pragma: no cover — registry 缺失/损坏时安全降级
        logger.warning("note_wp_mapping: registry unavailable, using legacy fallback")
    return dict(_LEGACY_DEFAULT_WP_MAPPING)


DEFAULT_WP_MAPPING = _build_default_wp_mapping()


async def _apply_final_note_formulas(
    db: AsyncSession, project_id: UUID, year: int, sections: list[str],
) -> dict[str, Any]:
    """refill 后执行每张表的预设/用户公式，保证公式读取的是最终披露明细。"""
    from app.services.note_workpaper_pull_service import _apply_note_formulas

    runs = await _apply_note_formulas(db, project_id, year, list(dict.fromkeys(sections)))
    errors = [f"附注公式失败 {section}: {item['error']}" for section, item in runs.items() if item.get("error")]
    return {
        "formula_updated": sum(int(item.get("updated") or 0) for item in runs.values()),
        "formula_sections": [section for section, item in runs.items() if int(item.get("updated") or 0) > 0],
        "formula_errors": errors,
    }


def _iter_formula_rows(table_data: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """按唯一真实容器遍历附注行，避免多表首表镜像被重复处理。

    workpaper/workpaper_html 的 ``sub_table_data`` 是可写真源；``_tables`` 只是
    读时投影，因此只要该字段存在就不读取投影。其它来源优先读取嵌套 ``_tables``，
    只有没有嵌套表时才兼容 legacy 顶层 ``rows``。
    """
    source = table_data.get("_source")
    if source in {"workpaper", "workpaper_html"} and "sub_table_data" in table_data:
        sub_tables = table_data.get("sub_table_data")
        if isinstance(sub_tables, dict):
            for key, value in sub_tables.items():
                if str(key).startswith("_"):
                    continue
                rows = value.get("rows") if isinstance(value, dict) else value
                if isinstance(rows, list):
                    yield from (row for row in rows if isinstance(row, dict))
        return

    tables = table_data.get("_tables")
    if isinstance(tables, list) and tables:
        for table in tables:
            if not isinstance(table, dict):
                continue
            rows = table.get("rows")
            if isinstance(rows, list):
                yield from (row for row in rows if isinstance(row, dict))
        return

    rows = table_data.get("rows")
    if isinstance(rows, list):
        yield from (row for row in rows if isinstance(row, dict))


def _row_values(row: dict[str, Any]) -> list:
    """行的数据列（不含标签列）：现行存 ``values``，早期行存 ``cells``。"""
    for key in ("values", "cells"):
        if isinstance(row.get(key), list):
            return row[key]
    return []


def _set_cell_mode(row: dict[str, Any], col_index: int, mode: str, value: float | None) -> bool:
    """改一个单元格的模式（``_cell_modes`` 按列索引建键，缺键 = 自动）与人工值；有改动返回 True。"""
    modes = row.get("_cell_modes") if isinstance(row.get("_cell_modes"), dict) else {}
    key = str(col_index)
    changed = False
    if modes.get(key, "auto") != mode:
        row["_cell_modes"] = {**modes, key: mode}
        changed = True
    values = _row_values(row)
    if value is not None and col_index < len(values) and values[col_index] != value:
        values[col_index] = value
        changed = True
    return changed


def _top_level_mirror(table_data: dict[str, Any], row: dict[str, Any]) -> dict[str, Any] | None:
    """``row`` 在 ``_tables[0]`` 里时返回顶层 ``rows`` 同位置的镜像行（标签一致才算；同一对象不算）。"""
    tables, top = table_data.get("_tables"), table_data.get("rows")
    if not (isinstance(tables, list) and tables and isinstance(tables[0], dict) and isinstance(top, list)):
        return None
    first = tables[0].get("rows")
    idx = next((i for i, r in enumerate(first) if r is row), None) if isinstance(first, list) else None
    if idx is None or idx >= len(top) or not isinstance(top[idx], dict) or top[idx] is row:
        return None
    return top[idx] if top[idx].get("label") == row.get("label") else None


class NoteWpMappingService:
    """附注-底稿映射服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_mapping(self, project_id: UUID) -> dict:
        """获取附注-底稿映射关系 — 优先从项目配置读取，降级用默认映射"""
        try:
            from app.models.core import Project
            result = await self.db.execute(
                sa.select(Project).where(Project.id == project_id)
            )
            project = result.scalar_one_or_none()
            if project and project.wizard_state:
                custom = project.wizard_state.get("note_wp_mapping")
                if custom and isinstance(custom, dict) and len(custom) > 0:
                    return custom
        except Exception:
            pass
        return dict(DEFAULT_WP_MAPPING)

    async def update_mapping(self, project_id: UUID, mapping: dict) -> dict:
        """更新映射关系 — 持久化到项目 wizard_state.note_wp_mapping"""
        try:
            from app.models.core import Project
            result = await self.db.execute(
                sa.select(Project).where(Project.id == project_id)
            )
            project = result.scalar_one_or_none()
            if not project:
                return {"error": "项目不存在", "mapping": mapping}

            ws = project.wizard_state or {}
            ws["note_wp_mapping"] = mapping
            project.wizard_state = ws
            # 标记 JSONB 字段已修改（SQLAlchemy 需要显式标记）
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(project, "wizard_state")
            await self.db.flush()
            logger.info(f"[NOTE_WP_MAPPING] updated: project={project_id} keys={len(mapping)}")
            return mapping
        except Exception as e:
            logger.warning(f"[NOTE_WP_MAPPING] update failed: {e}")
            return mapping

    async def refresh_from_workpapers(self, project_id: UUID, year: int) -> dict:
        """从底稿重新提数到附注 — 委托 DisclosureEngine.refill_sections 真实重算。

        按 DEFAULT_WP_MAPPING 命中的 sections 委托填充链重算，
        返回向后兼容的响应体（保留 refreshed/total_notes 键）。
        只 flush 不 commit（铁律：router 统一 commit）。

        Validates: Requirements 2.1, 2.2, 2.7, 1.3
        """
        from app.services.disclosure_engine import DisclosureEngine

        # 1. 获取映射，确定受影响的 note_section 列表
        mapping = await self.get_mapping(project_id)

        # 收集映射中有底稿前缀的所有 section
        affected_sections: list[str] = list(mapping.keys())

        # 2. 获取附注总数（向后兼容 total_notes）
        note_count_q = sa.select(sa.func.count()).select_from(DisclosureNote).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
        )
        total_notes = (await self.db.execute(note_count_q)).scalar() or 0

        # 3. 委托 DisclosureEngine.refill_sections 执行真实重算
        engine = DisclosureEngine(self.db)
        report = await engine.refill_sections(
            project_id, year, affected_sections, skip_manual=True
        )

        # 4. 最后执行附注表内预设/用户公式：headless 披露明细与 binding 已全部落到当前事务。
        formulas = await _apply_final_note_formulas(self.db, project_id, year, affected_sections)
        report.errors.extend(formulas["formula_errors"])

        # 5. 构造向后兼容的响应体
        return {
            "refreshed": report.cells_updated,
            "total_notes": total_notes,
            "sections_recomputed": report.sections_recomputed,
            "text_only_sections": report.text_only_sections,
            "errors": report.errors,
            **formulas,
        }

    async def refresh_section_from_workpapers(
        self, project_id: UUID, year: int, note_section: str
    ) -> dict:
        """只从底稿重算「单个章节」的科目数据（当前页面刷新用）。

        与 refresh_from_workpapers（项目级全量）区别：仅重算传入的 note_section，
        使「刷新当前页面」的前后端行为一致（后端只动当前节，不再全量写库）。
        委托 DisclosureEngine.refill_sections 传单元素列表；只 flush 不 commit。
        """
        from app.services.disclosure_engine import DisclosureEngine

        engine = DisclosureEngine(self.db)
        report = await engine.refill_sections(
            project_id, year, [note_section], skip_manual=True
        )
        formulas = await _apply_final_note_formulas(self.db, project_id, year, [note_section])
        report.errors.extend(formulas["formula_errors"])
        return {
            "refreshed": report.cells_updated,
            "total_notes": 1,
            "sections_recomputed": report.sections_recomputed,
            "text_only_sections": report.text_only_sections,
            "errors": report.errors,
            **formulas,
        }

    async def toggle_cell_mode(
        self, project_id: UUID, year: int, note_id: UUID, row_label: str, col_index: int, mode: str,
        manual_value: Decimal | float | None = None, *, user_id: UUID | None = None,
    ) -> dict:
        """切换单元格自动 / 手动模式：写行级 ``_cell_modes`` 边车（与清除公式 / 恢复自动同口径），人工值写回
        ``values``；真改了才以操作人盖「最近一次编辑」。

        原实现（spec disclosure-note-template-word-realignment Task 17 修）：①只按 id 取行 ⇒ 能改别的项目的附注；
        ②原地改 JSONB 再赋回同一对象，SQLAlchemy 判不出改动、从不落库；③把单元格换成
        ``{"value", "mode", "manual_value"}`` 字典写进 ``values``，没有读取方认这个形态（模式边车按列索引建键），
        一旦落库表格会显示成对象。
        """
        note = (await self.db.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.id == note_id,
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
                DisclosureNote.is_deleted == sa.false(),
            )
        )).scalar_one_or_none()
        if not note:
            return {"error": "附注不存在"}

        td = copy.deepcopy(note.table_data) if isinstance(note.table_data, dict) else {}
        target = next((r for r in _iter_formula_rows(td) if r.get("label") == row_label), None)
        if target is None:
            return {"error": f"附注表中没有「{row_label}」行"}
        if not 0 <= col_index < len(_row_values(target)):
            return {"error": f"「{row_label}」行没有第 {col_index + 1} 个数据列"}

        value = float(manual_value) if mode == "manual" and manual_value is not None else None
        changed = _set_cell_mode(target, col_index, mode, value)
        mirror = _top_level_mirror(td, target)
        if mirror is not None:  # 多表章节顶层 rows 是第一张表的镜像，一并改，免得两处读出不一样
            changed |= _set_cell_mode(mirror, col_index, mode, value)
        if changed:
            note.table_data = td
            flag_modified(note, "table_data")
            stamp_note_edit(note, user_id)
            await self.db.flush()
        return {"status": "ok", "mode": mode, "changed": changed}

    async def clear_formulas(self, project_id: UUID, year: int, note_section: str) -> int:
        """一键清除指定章节所有自动公式，切换为手动模式。

        保留当前数值不变，只改变 mode 标记。
        后续编辑不会被自动提数覆盖。
        """
        note = (await self.db.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
                DisclosureNote.note_section == note_section,
            )
        )).scalar_one_or_none()
        if not note or not note.table_data:
            return 0

        td = note.table_data
        cleared = 0

        for row in _iter_formula_rows(td):
            values = row.get("values")
            if not isinstance(values, list):
                values = row.get("cells")
            if not isinstance(values, list):
                # 业务键 raw 行没有位置化 values；它可能仍保留按列索引的模式
                # sidecar，模式键本身就是唯一可证明的列集合，不猜业务字段顺序。
                values = []
            cell_modes = row.get("_cell_modes")
            cell_modes = cell_modes if isinstance(cell_modes, dict) else {}

            keys = {str(key) for key in cell_modes}
            keys.update(str(i) for i in range(len(values)))
            for key in keys:
                if cell_modes.get(key, "auto") == "auto":
                    cell_modes[key] = "manual"
                    cleared += 1

            row["_cell_modes"] = cell_modes

        note.table_data = td
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(note, "table_data")
        await self.db.flush()

        logger.info(f"[CLEAR_FORMULAS] project={project_id} section={note_section} cleared={cleared}")
        return cleared

    async def restore_auto_mode(self, project_id: UUID, year: int, note_section: str) -> int:
        """恢复指定章节为自动提数模式。

        将所有 manual 单元格恢复为 auto，并从底稿重新提取数据。
        """
        note = (await self.db.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
                DisclosureNote.note_section == note_section,
            )
        )).scalar_one_or_none()
        if not note or not note.table_data:
            return 0

        td = note.table_data
        restored = 0

        for row in _iter_formula_rows(td):
            cell_modes = row.get("_cell_modes")
            cell_modes = cell_modes if isinstance(cell_modes, dict) else {}
            for key, mode in list(cell_modes.items()):
                if mode == "manual":
                    cell_modes[key] = "auto"
                    restored += 1
            row["_cell_modes"] = cell_modes

        note.table_data = td
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(note, "table_data")
        await self.db.flush()

        # 触发从底稿重新提数
        await self.refresh_from_workpapers(project_id, year)

        logger.info(f"[RESTORE_AUTO] project={project_id} section={note_section} restored={restored}")
        return restored
