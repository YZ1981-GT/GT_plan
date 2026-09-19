"""多文件同名 sheet 内容合并/去重工具

spec workpaper-account-multifile-aggregation 需求 3：
- 同名 sheet 判重必须比**内容哈希**（单元格值），非仅名称
- 内容完全相同（GT_Custom 等）→ 去重保留一份
- 内容不同 → 按来源顺序合并为单一网格，区块间插入来源标识行

输出网格形状与 `wp_grid_extract.extract_grid` 一致
（cells/merged_cells/col_widths/max_row/max_col），前端 GtGridSheet/GtCNoteTable
可直接渲染。

Requirements: 3.1, 3.2, 3.3, 3.4
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app.services.wp_grid_extract import extract_grid

logger = logging.getLogger(__name__)


def _col_letter(c: int) -> str:
    """1-based 列号 → 字母（与 wp_grid_extract 一致）。"""
    letters = ""
    while c > 0:
        c, rem = divmod(c - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _file_mtime(file_path: str) -> float:
    try:
        return Path(file_path).stat().st_mtime
    except OSError:
        return 0.0


@lru_cache(maxsize=256)
def _content_hash_cached(file_path: str, sheet_name: str, mtime: float) -> str:
    """内容哈希实现（按 (file,sheet,mtime) 缓存）。mtime 入 key 保证文件改动后失效。"""
    grid = extract_grid(file_path, sheet_name)
    cells = grid.get("cells", {}) if isinstance(grid, dict) else {}
    # 仅对单元格值排序后哈希（忽略样式/列宽，聚焦内容是否相同）
    payload = sorted(
        (coord, str(cell.get("v", ""))) for coord, cell in cells.items()
    )
    digest = hashlib.md5(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return digest


def content_hash(file_path: str, sheet_name: str) -> str:
    """单元格值内容哈希（带 (mtime,sheet) LRU 缓存）。

    用于判重：两个源文件同名 sheet 的 content_hash 相同 ⇒ 内容相同（可去重）。
    """
    return _content_hash_cached(file_path, sheet_name, _file_mtime(file_path))


@dataclass
class AggregatedSheet:
    """同名 sheet 聚合结果。"""

    sheet_name: str
    source_files: list[str] = field(default_factory=list)
    is_merged: bool = False  # True=多源内容不同已合并；False=单源或去重后单份


def merge_or_dedup(sheet_name: str, occurrences: list[str]) -> AggregatedSheet:
    """对同名 sheet 的多个来源文件判重/合并。

    - occurrences 为该 sheet 名出现的全部源文件路径（按来源顺序）
    - 内容哈希全同 → 去重（保留首个，is_merged=False）
    - 存在不同内容 → 合并（保留全部去重后的源，is_merged=True）

    需求 3.2（比内容非比名）/ 3.3（相同去重）。
    """
    if not occurrences:
        return AggregatedSheet(sheet_name=sheet_name, source_files=[], is_merged=False)

    # 按内容哈希去重，保留来源顺序
    seen_hashes: dict[str, str] = {}  # hash → first file
    unique_files: list[str] = []
    for f in occurrences:
        try:
            h = content_hash(f, sheet_name)
        except Exception as e:  # noqa: BLE001 — 哈希失败退化为按名去重（保留该源）
            logger.warning("内容哈希失败 %s/%s: %s（退化按名去重）", f, sheet_name, e)
            h = f  # 用路径作 key，等价于不与其他源合并
        if h not in seen_hashes:
            seen_hashes[h] = f
            unique_files.append(f)

    is_merged = len(unique_files) > 1
    return AggregatedSheet(
        sheet_name=sheet_name,
        source_files=unique_files,
        is_merged=is_merged,
    )


def _shift_grid(grid: dict, row_offset: int) -> tuple[dict, list, int]:
    """把一个网格的所有 cells/merged_cells 行号下移 row_offset。

    返回 (shifted_cells, shifted_merged, block_max_row)。
    """
    shifted_cells: dict = {}
    block_max_row = 0
    for _coord, cell in (grid.get("cells") or {}).items():
        r = int(cell.get("r", 0)) + row_offset
        c = int(cell.get("c", 0))
        block_max_row = max(block_max_row, r)
        new_coord = f"{_col_letter(c)}{r}"
        shifted_cells[new_coord] = {**cell, "r": r, "c": c}

    shifted_merged: list = []
    for mr in grid.get("merged_cells") or []:
        s = mr.get("s", {})
        e = mr.get("e", {})
        shifted_merged.append({
            "s": {"r": int(s.get("r", 0)) + row_offset, "c": int(s.get("c", 0))},
            "e": {"r": int(e.get("r", 0)) + row_offset, "c": int(e.get("c", 0))},
        })
    return shifted_cells, shifted_merged, block_max_row


def _source_label(file_path: str) -> str:
    """从源文件路径取简短来源标识（文件名去扩展名）。"""
    return Path(file_path).stem


def merge_sheet_content(
    source_files: list[str],
    sheet_name: str,
    component_type: str = "c-note-table",
) -> dict:
    """多源同名 sheet 内容纵向拼接为单一网格 html_data。

    区块之间插入一行"来源标识"（合并整行，标注来源文件名），保留审计轨迹
    （需求 3.1）。单源直接返回其网格。

    输出形状与 extract_grid 一致：cells/merged_cells/col_widths/max_row/max_col。
    """
    empty = {"cells": {}, "merged_cells": [], "col_widths": {}, "max_row": 0, "max_col": 0}
    if not source_files:
        return empty

    grids: list[dict] = []
    for f in source_files:
        try:
            g = extract_grid(f, sheet_name)
        except Exception as e:  # noqa: BLE001 — 单源提取失败跳过该源，不阻断
            logger.warning("merge 提取网格失败 %s/%s: %s", f, sheet_name, e)
            continue
        if isinstance(g, dict) and (g.get("cells")):
            grids.append({"_file": f, **g})

    if not grids:
        return empty
    if len(grids) == 1:
        g = {k: v for k, v in grids[0].items() if k != "_file"}
        return g

    merged_cells_all: list = []
    cells_all: dict = {}
    col_widths_all: dict = {}
    max_col_all = 0
    cur_row = 0

    for idx, g in enumerate(grids):
        file_path = g.get("_file", "")
        g_max_col = int(g.get("max_col", 0))
        max_col_all = max(max_col_all, g_max_col)
        col_widths_all.update(g.get("col_widths") or {})

        # 来源标识行（首块也加，便于审计区分来源）
        cur_row += 1
        label_coord = f"A{cur_row}"
        cells_all[label_coord] = {
            "v": f"【来源：{_source_label(file_path)}】",
            "r": cur_row,
            "c": 1,
            "style": {"bold": True, "align": "left", "source_label": True},
        }
        if g_max_col > 1:
            merged_cells_all.append({
                "s": {"r": cur_row, "c": 1},
                "e": {"r": cur_row, "c": g_max_col},
            })

        # 块内容下移到来源标识行之后
        shifted_cells, shifted_merged, block_max_row = _shift_grid(g, cur_row)
        cells_all.update(shifted_cells)
        merged_cells_all.extend(shifted_merged)
        cur_row = block_max_row

    return {
        "cells": cells_all,
        "merged_cells": merged_cells_all,
        "col_widths": col_widths_all,
        "max_row": cur_row,
        "max_col": max_col_all,
        "is_merged": True,
        "merged_source_count": len(grids),
    }
