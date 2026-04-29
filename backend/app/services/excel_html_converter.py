"""Excel ↔ HTML 互转引擎 — 双格式保存 + ONLYOFFICE 联动

核心流程：
1. Excel → structure.json → HTML（在线编辑）
2. HTML 编辑 → structure.json 更新 → Excel 回写
3. ONLYOFFICE 编辑 → WOPI put_file → 自动同步 structure.json

structure.json 是权威数据源，HTML 和 Excel 都从它生成。
取数公式绑定在 structure.json 的单元格上，与格式无关。

═══ structure.json 格式 ═══
{
    "sheets": [{
        "name": "Sheet1",
        "cols": [{"width": 100}, ...],
        "rows": [{"height": 20}, ...],
        "cells": {
            "0:0": {"value": "项目", "style": {...}, "formula": null, "fetch_rule_id": null},
            "0:1": {"value": 1234.56, "style": {...}, "formula": "=SUM(B2:B5)", "fetch_rule_id": "uuid"},
        },
        "merges": [{"start_row": 0, "start_col": 0, "end_row": 0, "end_col": 2}],
    }],
    "metadata": {"source": "upload", "created_at": "...", "version": 1}
}
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)


# ═══ Excel → structure.json ═══

def excel_to_structure(file_path: str, max_rows: int = 200, max_cols: int = 30) -> dict:
    """解析 Excel 文件为 structure.json 格式

    Args:
        file_path: Excel 文件路径
        max_rows: 最大解析行数（防止大文件卡死）
        max_cols: 最大解析列数

    Returns:
        structure.json 字典
    """
    import openpyxl
    from openpyxl.utils import get_column_letter

    wb = openpyxl.load_workbook(file_path, data_only=False)
    sheets = []

    for ws in wb.worksheets:
        sheet_data = {
            "name": ws.title,
            "cols": [],
            "rows": [],
            "cells": {},
            "merges": [],
        }

        # 列宽
        for col_idx in range(1, min(max_cols + 1, ws.max_column or 1) + 1):
            letter = get_column_letter(col_idx)
            width = ws.column_dimensions[letter].width or 10
            sheet_data["cols"].append({"width": round(width * 7.5)})  # Excel宽度→像素

        # 行高
        actual_rows = min(max_rows, ws.max_row or 0)
        for row_idx in range(1, actual_rows + 1):
            height = ws.row_dimensions[row_idx].height or 20
            sheet_data["rows"].append({"height": round(height)})

        # 单元格数据
        for row in ws.iter_rows(min_row=1, max_row=actual_rows, max_col=min(max_cols, ws.max_column or 1)):
            for cell in row:
                if cell.value is None and not cell.font.bold:
                    continue  # 跳过完全空白单元格

                r = cell.row - 1  # 转为0-indexed
                c = cell.column - 1
                key = f"{r}:{c}"

                cell_data: dict[str, Any] = {
                    "value": _serialize_value(cell.value),
                    "formula": str(cell.value) if isinstance(cell.value, str) and cell.value.startswith("=") else None,
                }

                # 样式提取
                style = _extract_style(cell)
                if style:
                    cell_data["style"] = style

                sheet_data["cells"][key] = cell_data

        # 合并单元格
        for merge_range in ws.merged_cells.ranges:
            sheet_data["merges"].append({
                "start_row": merge_range.min_row - 1,
                "start_col": merge_range.min_col - 1,
                "end_row": merge_range.max_row - 1,
                "end_col": merge_range.max_col - 1,
            })

        sheets.append(sheet_data)

    wb.close()

    return {
        "sheets": sheets,
        "metadata": {
            "source": "excel_upload",
            "source_file": Path(file_path).name,
            "created_at": datetime.utcnow().isoformat(),
            "version": 1,
            "sheet_count": len(sheets),
        },
    }


# ═══ structure.json → HTML ═══

def structure_to_html(structure: dict, sheet_index: int = 0, editable: bool = False) -> str:
    """将 structure.json 渲染为 HTML 表格

    Args:
        structure: structure.json 字典
        sheet_index: 要渲染的 sheet 索引
        editable: 是否生成可编辑的 HTML（contenteditable）

    Returns:
        HTML 字符串
    """
    sheets = structure.get("sheets", [])
    if sheet_index >= len(sheets):
        return "<p>无数据</p>"

    sheet = sheets[sheet_index]
    cells = sheet.get("cells", {})
    merges = sheet.get("merges", [])
    cols = sheet.get("cols", [])
    rows = sheet.get("rows", [])

    # 构建合并单元格映射
    merge_map: dict[str, dict] = {}  # "r:c" → merge info
    skip_cells: set[str] = set()
    for m in merges:
        key = f"{m['start_row']}:{m['start_col']}"
        merge_map[key] = m
        for r in range(m["start_row"], m["end_row"] + 1):
            for c in range(m["start_col"], m["end_col"] + 1):
                if f"{r}:{c}" != key:
                    skip_cells.add(f"{r}:{c}")

    # 确定表格尺寸
    max_row = len(rows) if rows else _get_max_dimension(cells, 0)
    max_col = len(cols) if cols else _get_max_dimension(cells, 1)

    # 生成 HTML
    html_parts = ['<table class="gt-excel-table" border="1" cellspacing="0" cellpadding="4">']

    # colgroup
    if cols:
        html_parts.append("<colgroup>")
        for col in cols:
            html_parts.append(f'<col style="width:{col.get("width", 80)}px">')
        html_parts.append("</colgroup>")

    for r in range(max_row):
        row_height = rows[r].get("height", 20) if r < len(rows) else 20
        html_parts.append(f'<tr style="height:{row_height}px">')

        for c in range(max_col):
            key = f"{r}:{c}"
            if key in skip_cells:
                continue

            cell = cells.get(key, {})
            value = cell.get("value", "")
            style = cell.get("style", {})
            formula = cell.get("formula")
            fetch_rule_id = cell.get("fetch_rule_id")

            # 构建 td 属性
            attrs = []
            if key in merge_map:
                m = merge_map[key]
                rowspan = m["end_row"] - m["start_row"] + 1
                colspan = m["end_col"] - m["start_col"] + 1
                if rowspan > 1:
                    attrs.append(f'rowspan="{rowspan}"')
                if colspan > 1:
                    attrs.append(f'colspan="{colspan}"')

            # 样式
            css = _style_to_css(style)
            if css:
                attrs.append(f'style="{css}"')

            # 数据属性（供前端取数联动）
            attrs.append(f'data-cell="{key}"')
            if formula:
                attrs.append(f'data-formula="{_escape_html(formula)}"')
            if fetch_rule_id:
                attrs.append(f'data-fetch-rule="{fetch_rule_id}"')

            # 可编辑
            if editable:
                attrs.append('contenteditable="true"')

            attr_str = " ".join(attrs)
            display_value = _format_display_value(value)
            html_parts.append(f"<td {attr_str}>{display_value}</td>")

        html_parts.append("</tr>")

    html_parts.append("</table>")
    return "\n".join(html_parts)


# ═══ HTML 编辑结果 → structure.json 更新 ═══

def update_structure_from_edits(structure: dict, edits: list[dict], sheet_index: int = 0) -> dict:
    """将前端编辑结果更新到 structure.json

    Args:
        structure: 原始 structure.json
        edits: 编辑列表 [{"cell": "0:1", "value": "新值", "formula": null}, ...]
        sheet_index: 编辑的 sheet 索引

    Returns:
        更新后的 structure.json
    """
    sheets = structure.get("sheets", [])
    if sheet_index >= len(sheets):
        return structure

    sheet = sheets[sheet_index]
    cells = sheet.get("cells", {})

    for edit in edits:
        key = edit.get("cell", "")
        if not key:
            continue

        if key not in cells:
            cells[key] = {}

        if "value" in edit:
            cells[key]["value"] = edit["value"]
        if "formula" in edit:
            cells[key]["formula"] = edit["formula"]
        if "fetch_rule_id" in edit:
            cells[key]["fetch_rule_id"] = edit["fetch_rule_id"]
        if "style" in edit:
            cells[key]["style"] = edit["style"]

    sheet["cells"] = cells
    structure["metadata"]["version"] = structure["metadata"].get("version", 0) + 1
    structure["metadata"]["last_edited_at"] = datetime.utcnow().isoformat()

    return structure


# ═══ structure.json → Excel 回写 ═══

def structure_to_excel(structure: dict, output_path: str, sheet_index: int | None = None) -> str:
    """将 structure.json 写回 Excel 文件

    Args:
        structure: structure.json 字典
        output_path: 输出 Excel 路径
        sheet_index: 指定 sheet（None=全部）

    Returns:
        输出文件路径
    """
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # 移除默认 sheet

    sheets = structure.get("sheets", [])
    target_sheets = [sheets[sheet_index]] if sheet_index is not None else sheets

    for sheet_data in target_sheets:
        ws = wb.create_sheet(title=sheet_data.get("name", "Sheet"))

        # 列宽
        for i, col in enumerate(sheet_data.get("cols", []), 1):
            letter = get_column_letter(i)
            ws.column_dimensions[letter].width = col.get("width", 80) / 7.5

        # 行高
        for i, row in enumerate(sheet_data.get("rows", []), 1):
            ws.row_dimensions[i].height = row.get("height", 20)

        # 单元格
        for key, cell_data in sheet_data.get("cells", {}).items():
            parts = key.split(":")
            r = int(parts[0]) + 1  # 转为1-indexed
            c = int(parts[1]) + 1

            cell = ws.cell(row=r, column=c)

            # 值或公式
            formula = cell_data.get("formula")
            if formula:
                cell.value = formula
            else:
                cell.value = cell_data.get("value")

            # 样式
            style = cell_data.get("style", {})
            if style:
                _apply_style_to_cell(cell, style)

        # 合并单元格
        for m in sheet_data.get("merges", []):
            ws.merge_cells(
                start_row=m["start_row"] + 1,
                start_column=m["start_col"] + 1,
                end_row=m["end_row"] + 1,
                end_column=m["end_col"] + 1,
            )

    wb.save(output_path)
    wb.close()
    return output_path


# ═══ ONLYOFFICE 联动：WOPI put_file 后同步 structure.json ═══

def sync_structure_from_excel(excel_path: str, structure_path: str) -> dict:
    """ONLYOFFICE 保存后，从 Excel 重新解析更新 structure.json

    保留用户自定义的 fetch_rule_id 绑定（Excel 中没有这个信息）。
    """
    # 解析新 Excel
    new_structure = excel_to_structure(excel_path)

    # 加载旧 structure（保留 fetch_rule_id 绑定）
    old_structure = {}
    sp = Path(structure_path)
    if sp.exists():
        try:
            old_structure = json.loads(sp.read_text(encoding="utf-8"))
        except Exception:
            pass

    # 合并：新值 + 旧的 fetch_rule_id
    if old_structure.get("sheets"):
        for si, new_sheet in enumerate(new_structure.get("sheets", [])):
            if si < len(old_structure["sheets"]):
                old_cells = old_structure["sheets"][si].get("cells", {})
                for key, new_cell in new_sheet.get("cells", {}).items():
                    old_cell = old_cells.get(key, {})
                    if old_cell.get("fetch_rule_id"):
                        new_cell["fetch_rule_id"] = old_cell["fetch_rule_id"]

    # 保留版本号递增
    old_version = old_structure.get("metadata", {}).get("version", 0)
    new_structure["metadata"]["version"] = old_version + 1
    new_structure["metadata"]["synced_from"] = "onlyoffice"
    new_structure["metadata"]["synced_at"] = datetime.utcnow().isoformat()

    # 保存
    sp.write_text(json.dumps(new_structure, ensure_ascii=False, indent=2), encoding="utf-8")

    return new_structure


# ═══ 内部辅助函数 ═══

def _serialize_value(value) -> Any:
    """序列化单元格值"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _extract_style(cell) -> dict | None:
    """提取单元格样式"""
    style = {}

    if cell.font:
        if cell.font.bold:
            style["bold"] = True
        if cell.font.italic:
            style["italic"] = True
        if cell.font.size:
            style["fontSize"] = cell.font.size
        if cell.font.name:
            style["fontFamily"] = cell.font.name
        if cell.font.color and cell.font.color.rgb and cell.font.color.rgb != "00000000":
            style["color"] = f"#{cell.font.color.rgb[-6:]}"

    if cell.alignment:
        if cell.alignment.horizontal:
            style["textAlign"] = cell.alignment.horizontal
        if cell.alignment.vertical:
            style["verticalAlign"] = cell.alignment.vertical

    if cell.fill and cell.fill.fgColor and cell.fill.fgColor.rgb and cell.fill.fgColor.rgb not in ("00000000", "FFFFFFFF"):
        style["backgroundColor"] = f"#{cell.fill.fgColor.rgb[-6:]}"

    if cell.number_format and cell.number_format != "General":
        style["numberFormat"] = cell.number_format

    return style if style else None


def _style_to_css(style: dict) -> str:
    """样式字典转 CSS"""
    parts = []
    if style.get("bold"):
        parts.append("font-weight:bold")
    if style.get("italic"):
        parts.append("font-style:italic")
    if style.get("fontSize"):
        parts.append(f"font-size:{style['fontSize']}pt")
    if style.get("fontFamily"):
        parts.append(f"font-family:{style['fontFamily']}")
    if style.get("color"):
        parts.append(f"color:{style['color']}")
    if style.get("textAlign"):
        parts.append(f"text-align:{style['textAlign']}")
    if style.get("backgroundColor"):
        parts.append(f"background-color:{style['backgroundColor']}")
    return ";".join(parts)


def _apply_style_to_cell(cell, style: dict):
    """将样式应用到 openpyxl 单元格"""
    from openpyxl.styles import Font, Alignment, PatternFill

    font_kwargs = {}
    if style.get("bold"):
        font_kwargs["bold"] = True
    if style.get("italic"):
        font_kwargs["italic"] = True
    if style.get("fontSize"):
        font_kwargs["size"] = style["fontSize"]
    if style.get("fontFamily"):
        font_kwargs["name"] = style["fontFamily"]
    if font_kwargs:
        cell.font = Font(**font_kwargs)

    align_kwargs = {}
    if style.get("textAlign"):
        align_kwargs["horizontal"] = style["textAlign"]
    if style.get("verticalAlign"):
        align_kwargs["vertical"] = style["verticalAlign"]
    if align_kwargs:
        cell.alignment = Alignment(**align_kwargs)

    if style.get("backgroundColor"):
        color = style["backgroundColor"].lstrip("#")
        cell.fill = PatternFill(start_color=color, end_color=color, fill_type="solid")


def _format_display_value(value) -> str:
    """格式化显示值"""
    if value is None:
        return ""
    if isinstance(value, float):
        if value == int(value):
            return f"{int(value):,}"
        return f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return _escape_html(str(value))


def _escape_html(s: str) -> str:
    """HTML 转义"""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _get_max_dimension(cells: dict, axis: int) -> int:
    """从 cells 字典推断最大行/列数"""
    max_val = 0
    for key in cells:
        parts = key.split(":")
        if len(parts) == 2:
            val = int(parts[axis]) + 1
            if val > max_val:
                max_val = val
    return max_val
