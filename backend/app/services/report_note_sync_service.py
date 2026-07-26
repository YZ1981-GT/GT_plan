"""报表与附注联动编辑服务

Requirements: 30.1-30.5（历史）
Spec: disclosure-note-formula-and-report-sync Wave3 (Task 4.3)
Reqs: 3.1 / 3.2 / 3.3 / 3.4 / 3.5 / 3.6 / 3.7 / 8.3 / 8.4

- sync_report_to_notes(project_id, year) — 同步报表金额到关联附注章节的公式单元格
  - **灰度开关 DISCLOSURE_NOTE_FORMULA_ENABLED**（默认 False）：
    关闭时逐字节保持当前 stub 行为（仅清 is_stale + validation_run/skipped_sections 硬编码，
    零回归 characterization 基线）；开启时经 ReportNoteLinkage 找目标单元格 → 写公式单元格
    → note_cell_merge 保留 manual/locked → 真实统计 → 触发 validate_all。
  - fail-open：异常不阻断 chain_workflow；幂等：相同报表数二次同步无额外副作用。
- mark_notes_stale_for_report_change(project_id, year) — 报表行次变更时标记关联附注 stale（不回归）
"""
from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import DisclosureNote, FinancialReport
from app.services.note_cell_merge import merge_table_data_preserving_cell_modes
from app.services.report_note_linkage import LinkTarget, ReportNoteLinkage

logger = logging.getLogger(__name__)


def _formula_enabled() -> bool:
    """灰度开关（默认 False = 保持 stub 行为，逐字节零回归）。"""
    try:
        from app.core.config import settings

        return bool(getattr(settings, "DISCLOSURE_NOTE_FORMULA_ENABLED", False))
    except Exception:  # pragma: no cover — 配置不可用时安全降级为关闭
        return False


def _to_number(x: Any) -> float | None:
    """报表金额（Decimal/int/float）安全转 float 供 JSONB 存储；否则 None。"""
    if x is None or isinstance(x, bool):
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _select_table(table_data: Any, table_index: int) -> dict[str, Any] | None:
    """按 table_index 选表：多表取 ``_tables[i]``，单表取自身。"""
    if not isinstance(table_data, dict):
        return None
    tables = table_data.get("_tables")
    if isinstance(tables, list) and tables:
        if 0 <= table_index < len(tables) and isinstance(tables[table_index], dict):
            return tables[table_index]
        return None
    return table_data


class ReportNoteSyncService:
    """报表与附注联动同步服务。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def sync_report_to_notes(self, project_id: UUID, year: int) -> dict:
        """同步报表最新数据到关联附注章节的公式单元格。

        灰度关闭（默认）→ stub 行为：仅清 is_stale，validation_run 硬编码 True、
        skipped_sections 硬编码 0（零回归基线）。
        灰度开启 → 真同步：经 ReportNoteLinkage 写公式单元格（保留 manual/locked），
        返回真实统计 ``{synced_sections, skipped_sections, cells_updated, validation_run}``。

        无报表/无附注一律返回 3-key stub（与历史一致）。
        """
        # 1. Load all report rows with data（两路径共用；无报表行提前返回，与历史一致）
        rpt_stmt = select(FinancialReport).where(
            FinancialReport.project_id == project_id,
            FinancialReport.year == year,
            FinancialReport.is_deleted == False,
            FinancialReport.current_period_amount != None,
        )
        rpt_result = await self.db.execute(rpt_stmt)
        report_rows = rpt_result.scalars().all()

        if not report_rows:
            return {"synced_sections": 0, "skipped_sections": 0, "validation_run": False}

        # 2. Load all note sections
        note_stmt = select(DisclosureNote).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.is_deleted == False,
        )
        note_result = await self.db.execute(note_stmt)
        notes = note_result.scalars().all()

        if not notes:
            return {"synced_sections": 0, "skipped_sections": 0, "validation_run": False}

        # 灰度开关：关闭时逐字节保持 stub 行为（零回归 characterization 基线）
        if not _formula_enabled():
            return await self._sync_stub(notes)

        return await self._sync_real(project_id, year, report_rows, notes)

    # ------------------------------------------------------------------
    # 灰度关闭：stub 行为（仅清 is_stale + 硬编码统计）—— 与历史逐字节等价
    # ------------------------------------------------------------------

    async def _sync_stub(self, notes: list) -> dict:
        synced_count = 0
        for note in notes:
            if hasattr(note, "is_stale") and note.is_stale:
                note.is_stale = False
                synced_count += 1

        # If no stale notes, still count as synced
        if synced_count == 0:
            synced_count = len(notes)

        # Run basic validation after sync（历史硬编码）
        validation_run = True

        await self.db.flush()

        return {
            "synced_sections": synced_count,
            "skipped_sections": 0,
            "validation_run": validation_run,
        }

    # ------------------------------------------------------------------
    # 灰度开启：真同步（ReportNoteLinkage + note_cell_merge + validate_all）
    # ------------------------------------------------------------------

    async def _sync_real(
        self, project_id: UUID, year: int, report_rows: list, notes: list
    ) -> dict:
        # 报表数据 row_code → amount（current_period_amount）
        report_data: dict[str, float] = {}
        for r in report_rows:
            rc = getattr(r, "row_code", None)
            amt = _to_number(getattr(r, "current_period_amount", None))
            if isinstance(rc, str) and rc and amt is not None:
                report_data[rc] = amt  # 同 row_code 后者覆盖（跨 report_type 罕见）

        linkage = ReportNoteLinkage()
        synced_sections = 0
        cells_updated = 0
        matched_rows: set[str] = set()

        for note in notes:
            try:
                targets = linkage.report_targets_in_note(note)
                if not targets:
                    continue
                new_td, written, matched = self._apply_report_values(
                    note, targets, report_data
                )
                matched_rows |= matched
                if written > 0:
                    # note_cell_merge 保留 manual/locked（Req3.2，双保险）
                    note.table_data = merge_table_data_preserving_cell_modes(
                        note.table_data, new_td
                    )
                    cells_updated += written
                    synced_sections += 1
                # 同步过的节按实际清 stale（Req3.5）
                if hasattr(note, "is_stale"):
                    note.is_stale = False
            except Exception as err:
                # 单节隔离 fail-open（Req3.4/3.7），不影响其余
                logger.warning(
                    "sync_report_to_notes: section %s failed (skipped): %s",
                    getattr(note, "note_section", None), err,
                )
                continue

        # 无 linkage 目标的报表行 → skipped（Req3.4 / Property 8，可审计）
        skipped_sections = sum(1 for rc in report_data if rc not in matched_rows)

        # 触发附注校验（Req3.5 / Req6）；fail-open（不阻断 chain_workflow，Req3.7）
        validation_run = False
        try:
            from app.services.note_validation_engine import NoteValidationEngine

            await NoteValidationEngine(self.db).validate_all(project_id, year)
            validation_run = True
        except Exception as err:
            logger.warning(
                "sync_report_to_notes: validate_all failed (fail-open): %s", err
            )

        await self.db.flush()

        return {
            "synced_sections": synced_sections,
            "skipped_sections": skipped_sections,
            "cells_updated": cells_updated,
            "validation_run": validation_run,
        }

    @staticmethod
    def _apply_report_values(
        note: Any,
        targets: list[LinkTarget],
        report_data: dict[str, float],
    ) -> tuple[dict[str, Any], int, set[str]]:
        """把报表金额写入 note 的 REPORT 目标单元格（返回新 table_data，不就地改）。

        - 仅写 Cell_Mode 非 manual/locked 的公式单元格（manual/locked 跳过，Req3.2）。
        - 坐标越界 / 表越界 → 跳过（不写非目标单元格，Req4.3）。
        - matched：成功定位到有效目标单元格的 row_code（无论是否写入，用于 skipped 判定）。
        """
        td: dict[str, Any] = (
            deepcopy(note.table_data) if isinstance(note.table_data, dict) else {}
        )
        written = 0
        matched: set[str] = set()

        for t in targets:
            rc = t.row_code
            if rc not in report_data:
                continue
            tbl = _select_table(td, t.table_index)
            if not isinstance(tbl, dict):
                continue
            rows = tbl.get("rows")
            if not isinstance(rows, list) or not (0 <= t.row_idx < len(rows)):
                continue
            row = rows[t.row_idx]
            if not isinstance(row, dict):
                continue
            values = row.get("values")
            if not isinstance(values, list) or not (0 <= t.col_idx < len(values)):
                continue
            # 有效目标已定位（无论 manual/locked）→ 该报表行视为有 linkage（不计 skipped）
            matched.add(rc)
            mode = (row.get("_cell_modes") or {}).get(str(t.col_idx))
            if mode in ("manual", "locked"):
                continue
            values[t.col_idx] = report_data[rc]
            written += 1

        return td, written, matched

    async def mark_notes_stale_for_report_change(
        self,
        project_id: UUID,
        year: int,
        *,
        changed_row_codes: set[str] | None = None,
    ) -> int:
        """报表行次变更时标记**关联**附注为 stale（P0-3 粒度化）。

        历史实现是"一刀切全项目附注 is_stale=true"，实测某项目 181/181 全亮
        → 标记退化成背景噪声。现按关联关系分级：

        1. 经 ``ReportNoteLinkage`` 求每章节关联的报表行次（Cell_Binding + 配置）；
           ``changed_row_codes`` 给出时只标命中交集的章节，否则标"有任何 REPORT
           关联"的章节；``stale_source='report'``。
        2. **全项目一个 linkage 目标都没有**（当前多数项目如此）→ 保守回退全量标记，
           避免丢失提示；``stale_source='report_fallback'``（前端可据此弱化呈现）。

        任何异常 fail-open：回退历史全量标记语义，不阻断调用方。

        Returns: 被标记的章节数
        """
        try:
            note_stmt = select(DisclosureNote).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
                DisclosureNote.is_deleted == False,
            )
            notes = (await self.db.execute(note_stmt)).scalars().all()
            if not notes:
                return 0

            linkage = ReportNoteLinkage()
            targeted: list[Any] = []
            any_linkage = False
            for note in notes:
                rows = linkage.report_rows_for_note(note)
                if rows:
                    any_linkage = True
                    if changed_row_codes is None or (rows & set(changed_row_codes)):
                        targeted.append(note)

            if any_linkage:
                for note in targeted:
                    note.is_stale = True
                    note.stale_source = "report"
                await self.db.flush()
                return len(targeted)

            # 无任何 linkage → 保守全量（历史语义），但标注为 fallback
            for note in notes:
                note.is_stale = True
                note.stale_source = "report_fallback"
            await self.db.flush()
            return len(notes)
        except Exception as e:
            logger.warning("mark_notes_stale_for_report_change error: %s", e)
            # fail-open：退回历史全量 UPDATE（不带来源标注）
            try:
                stmt = (
                    update(DisclosureNote)
                    .where(
                        DisclosureNote.project_id == project_id,
                        DisclosureNote.year == year,
                        DisclosureNote.is_deleted == False,
                    )
                    .values(is_stale=True)
                )
                result = await self.db.execute(stmt)
                return result.rowcount
            except Exception:
                return 0
