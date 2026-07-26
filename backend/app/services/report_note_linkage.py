"""ReportNoteLinkage — 报表行 → 附注单元格的单一真源映射（Wave 3 / Task 4.1）.

Spec:   .kiro/specs/disclosure-note-formula-and-report-sync/ Wave3 (Task 4.1/4.2)
Design: 决策3（Report_Note_Linkage 单一真源，Cell_Binding 优先 / config 回退）
Reqs:   4.1 / 4.2 / 4.3 / 4.4

单一真源（Design 决策3）
------------------------
经查证全平台无「报表行→附注单元格」权威映射。本类收敛为唯一真源：

  ① **优先**：附注 ``table_data`` 单元格内嵌的 REPORT Cell_Binding
     （``_cell_meta[str(col)]["binding"]`` 且 ``source=='report' && row_code==X``）
     —— 就地绑定天然单一真源、随模板演进（Req4.1/4.2）。
  ② **回退**：``backend/data/disclosure/report_note_linkage.json``
     （data-driven，仅覆盖模板未内嵌绑定的章节，按 note_section 增量维护）。

优先级（Req4.2 / Property 7）
----------------------------
同一 row_code 在 Cell_Binding 与 config 都有目标时以 Cell_Binding 为准：
若该 row_code 存在任一 Cell_Binding 目标，则**忽略**该 row_code 的 config 目标
（就地绑定优先于集中配置）。这保证报表→附注同步（Req3）与表内 REPORT 公式求值
（Req1.3）经 ``report_rows_for_note`` / ``targets_for_report_row`` 取到**相同**目标集
（Req4.4，杜绝两套映射漂移）。

fail-safe（Req4.3）
-------------------
- config 文件缺失 / 非法 JSON → 空映射（fail-open，不抛）。
- 坐标非法 / 缺失 → 跳过该项（不抛、不写入非目标单元格）。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

logger = logging.getLogger(__name__)

# report_note_linkage.json 回退真源路径（backend/data/disclosure/）
_CONFIG_PATH: Path = (
    Path(__file__).resolve().parent.parent.parent
    / "data"
    / "disclosure"
    / "report_note_linkage.json"
)

# R{row}C{col}（1-based Excel 风格）解析
_CELL_RE = re.compile(r"\s*[Rr](\d+)[Cc](\d+)\s*")


@dataclass(frozen=True)
class LinkTarget:
    """一个报表行金额应写入的附注单元格目标坐标。

    - ``note_section`` / ``note_id``：定位附注章节
    - ``table_index`` / ``row_idx`` / ``col_idx``：0-based 单元格坐标（多表按 table_index）
    - ``row_code``：来源报表行次
    - ``origin``：``"binding"``（内嵌 Cell_Binding）/ ``"config"``（回退配置），供审计溯源
    """

    note_section: str
    table_index: int
    row_idx: int
    col_idx: int
    row_code: str
    origin: str
    note_id: Any = None


def _parse_cell(cell: Any) -> tuple[int, int] | None:
    """解析 ``R{r}C{c}``（1-based）→ (row_idx, col_idx)（0-based）；非法 → None."""
    if not isinstance(cell, str):
        return None
    m = _CELL_RE.fullmatch(cell)
    if not m:
        return None
    r = int(m.group(1)) - 1
    c = int(m.group(2)) - 1
    if r < 0 or c < 0:
        return None
    return (r, c)


def _iter_tables(table_data: Any) -> Iterator[tuple[int, dict[str, Any]]]:
    """产出 (table_index, table)；多表走 ``_tables``，单表走自身（index=0）。"""
    if not isinstance(table_data, dict):
        return
    tables = table_data.get("_tables")
    if isinstance(tables, list) and tables:
        for i, tbl in enumerate(tables):
            if isinstance(tbl, dict):
                yield i, tbl
    else:
        yield 0, table_data


class ReportNoteLinkage:
    """报表行 ↔ 附注单元格 linkage（Cell_Binding 优先 / config 回退，单一真源）。"""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config: dict[str, list[dict[str, Any]]] = (
            self._normalize_config(config)
            if config is not None
            else self._load_config()
        )

    # ------------------------------------------------------------------
    # config 加载（fail-open）
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_config(raw: Any) -> dict[str, list[dict[str, Any]]]:
        """规范化配置：仅保留 row_code(非 _ 前缀) → list[entry dict]。"""
        if not isinstance(raw, dict):
            return {}
        out: dict[str, list[dict[str, Any]]] = {}
        for k, v in raw.items():
            # 以 _ 开头的键为元数据/示例，忽略（Req4.2/4.3）
            if not isinstance(k, str) or k.startswith("_"):
                continue
            if isinstance(v, list):
                out[k] = [e for e in v if isinstance(e, dict)]
        return out

    @classmethod
    def _load_config(cls) -> dict[str, list[dict[str, Any]]]:
        """从 report_note_linkage.json 加载；缺失/非法 → {}（fail-open, Req4.3）。"""
        try:
            if not _CONFIG_PATH.exists():
                return {}
            with open(_CONFIG_PATH, encoding="utf-8") as f:
                raw = json.load(f)
            return cls._normalize_config(raw)
        except Exception as err:  # pragma: no cover — 环境/IO 异常安全降级
            logger.warning(
                "ReportNoteLinkage: load config failed (%s); using empty mapping", err
            )
            return {}

    # ------------------------------------------------------------------
    # Cell_Binding 扫描（优先真源）
    # ------------------------------------------------------------------

    @staticmethod
    def _iter_binding_targets(note: Any) -> list[LinkTarget]:
        """扫 note.table_data 各单元格 ``_cell_meta[col].binding`` 中 source=='report'。

        col_idx = ``_cell_meta`` 键（就地绑定所在列）；row_idx = 行在 rows 中的位置。
        坐标非法（col 键非整数）→ 跳过（Req4.3）。
        """
        section = getattr(note, "note_section", None)
        if not isinstance(section, str) or not section:
            return []
        note_id = getattr(note, "id", None)
        table_data = getattr(note, "table_data", None)
        out: list[LinkTarget] = []
        for t_idx, tbl in _iter_tables(table_data):
            rows = tbl.get("rows")
            if not isinstance(rows, list):
                continue
            for r_idx, row in enumerate(rows):
                if not isinstance(row, dict):
                    continue
                meta = row.get("_cell_meta")
                if not isinstance(meta, dict):
                    continue
                for col_key, slot in meta.items():
                    if not isinstance(slot, dict):
                        continue
                    binding = slot.get("binding")
                    if not isinstance(binding, dict):
                        continue
                    if binding.get("source") != "report":
                        continue
                    row_code = binding.get("row_code")
                    if not (isinstance(row_code, str) and row_code):
                        continue
                    try:
                        col_idx = int(col_key)
                    except (TypeError, ValueError):
                        # 坐标非法 → 跳过并记录（Req4.3）
                        logger.debug(
                            "ReportNoteLinkage: skip invalid col key %r in note %s",
                            col_key, section,
                        )
                        continue
                    if col_idx < 0:
                        continue
                    out.append(
                        LinkTarget(
                            note_section=section,
                            table_index=t_idx,
                            row_idx=r_idx,
                            col_idx=col_idx,
                            row_code=row_code,
                            origin="binding",
                            note_id=note_id,
                        )
                    )
        return out

    # ------------------------------------------------------------------
    # config 目标（回退真源）
    # ------------------------------------------------------------------

    def _iter_config_targets(self, note: Any) -> list[LinkTarget]:
        """回退 config：产出 note_section 命中本 note 的 LinkTarget。坐标非法跳过。"""
        section = getattr(note, "note_section", None)
        if not isinstance(section, str) or not section:
            return []
        note_id = getattr(note, "id", None)
        out: list[LinkTarget] = []
        for row_code, entries in self._config.items():
            for e in entries:
                if e.get("note_section") != section:
                    continue
                coord = _parse_cell(e.get("cell"))
                if coord is None:
                    logger.debug(
                        "ReportNoteLinkage: skip invalid cell %r for row %s section %s",
                        e.get("cell"), row_code, section,
                    )
                    continue
                t_idx = e.get("table_index")
                if not isinstance(t_idx, int) or t_idx < 0:
                    t_idx = 0
                out.append(
                    LinkTarget(
                        note_section=section,
                        table_index=t_idx,
                        row_idx=coord[0],
                        col_idx=coord[1],
                        row_code=row_code,
                        origin="config",
                        note_id=note_id,
                    )
                )
        return out

    # ------------------------------------------------------------------
    # 对外 API
    # ------------------------------------------------------------------

    def report_targets_in_note(self, note: Any) -> list[LinkTarget]:
        """本 note 内所有 REPORT 目标单元格（Cell_Binding 优先，config 回退）。

        Cell_Binding 覆盖到的 row_code 忽略其 config 目标（Req4.2 就地绑定优先）。
        """
        binding = self._iter_binding_targets(note)
        binding_rows = {t.row_code for t in binding}
        config = [
            t for t in self._iter_config_targets(note) if t.row_code not in binding_rows
        ]
        return binding + config

    def report_rows_for_note(self, note: Any) -> set[str]:
        """反向：本 note 关联的报表行次集合（供表内 REPORT 公式求值共用同一 linkage）。"""
        return {t.row_code for t in self.report_targets_in_note(note)}

    def targets_for_report_row(
        self, notes: list[Any], row_code: str
    ) -> list[LinkTarget]:
        """跨 notes 求某报表行的所有目标单元格。

        优先级（Req4.2 / Property 7）：若该 row_code 存在任一 Cell_Binding 目标，
        则仅返回 Cell_Binding 目标（忽略 config）；否则返回 config 目标。
        """
        if not isinstance(row_code, str) or not row_code:
            return []
        binding: list[LinkTarget] = []
        config: list[LinkTarget] = []
        for note in notes or []:
            for t in self._iter_binding_targets(note):
                if t.row_code == row_code:
                    binding.append(t)
            for t in self._iter_config_targets(note):
                if t.row_code == row_code:
                    config.append(t)
        return binding if binding else config

    # ------------------------------------------------------------------
    # 只读诊断（spec disclosure-note-formula-data-population Task 5.1 / Req4）
    # ------------------------------------------------------------------

    def diagnose_missing_write_linkage(
        self,
        notes: list[Any],
        *,
        cross_check_sections: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        """列出「有报表↔附注勾稽关系但无写值 linkage」的章节（**只读**，不写入）。

        决策 1（用户已拍板）：报表↔附注只做校验不做写值 → 某章节
        ``cells_updated=0`` 是**正确行为**而非失败。本诊断把它显性化，供逐节人工
        评估是否确需写值映射（若需，按 ``report_note_linkage.json`` 的 ``_rules``
        逐节增量维护，**禁止批量臆造**）。

        Args:
            notes: 该项目/年度的附注对象列表（需有 ``note_section`` / ``table_data``）
            cross_check_sections: 存在勾稽关系的章节集合；缺省时从预设库
                （``note:{章节}`` 的 ``logic_check`` 条目）读取，fail-open。

        Returns:
            每项 ``{note_section, has_cross_check, write_linkage_targets,
            binding_targets, config_targets, reason}``；只呈现不修改任何数据。
        """
        if cross_check_sections is None:
            cross_check_sections = self._load_cross_check_sections()

        out: list[dict[str, Any]] = []
        for note in notes or []:
            section = getattr(note, "note_section", None)
            if not isinstance(section, str) or not section:
                continue
            binding_targets = self._iter_binding_targets(note)
            config_targets = self._iter_config_targets(note)
            total = len(binding_targets) + len(config_targets)
            has_cc = section in cross_check_sections
            if total > 0 or not has_cc:
                continue
            out.append(
                {
                    "note_section": section,
                    "has_cross_check": True,
                    "write_linkage_targets": 0,
                    "binding_targets": 0,
                    "config_targets": 0,
                    "reason": (
                        "该章节有报表↔附注勾稽（logic_check）但无写值 linkage："
                        "按决策 1 报表不回写附注，cells_updated=0 属正确行为；"
                        "如确需写值请按源模板/审计口径逐节增量维护"
                        " report_note_linkage.json"
                    ),
                }
            )
        return out

    @staticmethod
    def _load_cross_check_sections() -> set[str]:
        """从预设库取存在报表↔附注勾稽的附注章节集合（fail-open 返回空集）。"""
        try:
            from app.services.formula_management.preset_library import (
                build_preset_library,
            )

            entries, _stats = build_preset_library()
        except Exception as err:  # pragma: no cover — 预设库不可用时安全降级
            logger.warning(
                "ReportNoteLinkage: load preset library failed (%s); "
                "cross-check sections unknown",
                err,
            )
            return set()

        out: set[str] = set()
        for e in entries:
            page_key = getattr(e, "page_key", "") or ""
            if not page_key.startswith("note:"):
                continue
            if getattr(e, "formula_type", "") != "logic_check":
                continue
            out.add(page_key[len("note:") :])
        return out


__all__ = ["ReportNoteLinkage", "LinkTarget"]
