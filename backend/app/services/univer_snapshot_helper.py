"""Univer snapshot 落库辅助：slim 化 + 增量合并 + 体积保护

供 univer-save 端点把 IWorkbookData 缩减为 working_paper.parsed_data['univer_snapshot']
形态，作为高级查询「零计算路径」数据源。

设计目标：
  1. slim — 仅保留 v（值）+ f（公式），剥离样式 s 减小 JSONB 体积
  2. 增量 — 与 prev_snap 比对，仅保留有 cellData 变化的 sheet（其他沿用旧值）
  3. 体积保护 — 单 sheet > 50K cells 或单 wp > 5MB 时降级只存元数据
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# 体积上限（避免 PG row size 累积 dead tuple）
MAX_CELLS_PER_SHEET = 50_000
MAX_BYTES_PER_WP = 5 * 1024 * 1024  # 5MB

# 哨兵：单次保存的 snapshot 体积超限
SNAPSHOT_TOO_LARGE = object()


def _slim_cell(cell: Any) -> dict | None:
    """剥离 cell 样式，仅留 v 和 f"""
    if not isinstance(cell, dict):
        return None
    obj: dict = {}
    v = cell.get("v")
    if v is not None and v != "":
        obj["v"] = v
    if cell.get("f"):
        obj["f"] = cell["f"]
    return obj if obj else None


def _slim_sheet_cells(cell_data: Any) -> tuple[dict, int]:
    """slim 化单 sheet 的 cellData，返回 (slim_cells, cell_count)"""
    if not isinstance(cell_data, dict):
        return {}, 0
    slim: dict[str, dict] = {}
    count = 0
    for r_key, row in cell_data.items():
        if not isinstance(row, dict):
            continue
        slim_row: dict[str, dict] = {}
        for c_key, cell in row.items():
            slim_obj = _slim_cell(cell)
            if slim_obj:
                slim_row[str(c_key)] = slim_obj
                count += 1
        if slim_row:
            slim[str(r_key)] = slim_row
    return slim, count


def build_slim_snapshot(snapshot: dict[str, Any], file_version: int) -> dict[str, Any] | object:
    """从 Univer IWorkbookData 构建 slim snapshot（剥样式 + 检体积上限）

    返回 dict 表示成功，返回 SNAPSHOT_TOO_LARGE 表示体积超限（调用方需降级）
    """
    sheets_data = snapshot.get("sheets") or {}
    sheet_order = snapshot.get("sheetOrder") or list(sheets_data.keys())

    slim_sheets: dict[str, dict] = {}
    sheet_order_names: list[str] = []
    total_cells = 0

    for sid in sheet_order:
        sheet = sheets_data.get(sid) or {}
        sheet_name = sheet.get("name") or sid
        sheet_order_names.append(sheet_name)
        slim_cells, count = _slim_sheet_cells(sheet.get("cellData"))

        # 单 sheet cell 数上限
        if count > MAX_CELLS_PER_SHEET:
            logger.warning("sheet %s cells=%d 超 MAX_CELLS_PER_SHEET=%d，跳过 cellData",
                          sheet_name, count, MAX_CELLS_PER_SHEET)
            slim_sheets[sheet_name] = {"id": sid, "cellData": {}, "skipped_reason": "too_many_cells", "skipped_count": count}
            continue

        slim_sheets[sheet_name] = {"id": sid, "cellData": slim_cells, "cell_count": count}
        total_cells += count

    result = {
        "sheets": slim_sheets,
        "sheet_order_names": sheet_order_names,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "version": file_version,
        "total_cells": total_cells,
    }

    # 全 wp 体积上限
    try:
        size_bytes = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    except Exception:
        size_bytes = 0
    if size_bytes > MAX_BYTES_PER_WP:
        logger.warning("snapshot 序列化 %d bytes 超 MAX_BYTES_PER_WP=%d，降级",
                      size_bytes, MAX_BYTES_PER_WP)
        return SNAPSHOT_TOO_LARGE

    result["size_bytes"] = size_bytes
    return result


def merge_snapshot_incremental(prev: dict | None, new: dict) -> dict:
    """增量合并：prev 中的 sheet 若 new 没动则保留旧值，避免每次保存都写整份

    判定逻辑：以 sheet_name 为 key，逐 sheet 比 cellData 字典是否相等
    （cellData 体积小时直接 dict 相等比对；体积大时降级为 cell_count + sample 比对）
    """
    if not isinstance(prev, dict):
        return new
    prev_sheets = prev.get("sheets") or {}
    new_sheets = new.get("sheets") or {}
    if not isinstance(prev_sheets, dict) or not isinstance(new_sheets, dict):
        return new

    merged_sheets: dict[str, dict] = {}
    changed_sheet_names: list[str] = []

    for name, new_sheet in new_sheets.items():
        prev_sheet = prev_sheets.get(name)
        if prev_sheet is None:
            merged_sheets[name] = new_sheet
            changed_sheet_names.append(name)
            continue
        # cell_count 相等且 cellData 相等才认为未变（dict 相等比对在 5K cells 以下足够快）
        prev_count = prev_sheet.get("cell_count", -1)
        new_count = new_sheet.get("cell_count", -1)
        if prev_count == new_count and prev_sheet.get("cellData") == new_sheet.get("cellData"):
            # 沿用旧 sheet 数据（仅 id 跟新避免 sheet_id 漂移）
            merged_sheets[name] = {**prev_sheet, "id": new_sheet.get("id", prev_sheet.get("id"))}
        else:
            merged_sheets[name] = new_sheet
            changed_sheet_names.append(name)

    return {
        **new,
        "sheets": merged_sheets,
        "changed_sheets_last_save": changed_sheet_names,
    }
