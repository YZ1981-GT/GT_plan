"""
Phase 0.1: openpyxl脚本读取L7其他非流动负债.xlsx全部8 sheet
提取结构 + 确认审定表L7-1(72公式)+明细表L7-2结构
产出：l7_structure_summary.json
"""

import json
import os
from pathlib import Path
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

# 源模板路径
XLSX_PATH = (
    r"D:\GT_plan\数据\致同通用审计程序及底稿模板（2025年修订）"
    r"\1.致同审计程序及底稿模板（2025年）"
    r"\4.风险应对-实质性程序（D-N）\L 债务循环\L7 其他非流动负债.xlsx"
)

OUTPUT_DIR = Path(__file__).parent
OUTPUT_PATH = OUTPUT_DIR / "l7_structure_summary.json"


def extract_sheet_structure(ws):
    """Extract structure of a single worksheet."""
    sheet_info = {
        "title": ws.title,
        "dimensions": ws.dimensions,
        "max_row": ws.max_row,
        "max_column": ws.max_column,
        "merged_cells": [str(mc) for mc in ws.merged_cells.ranges],
    }

    # Extract headers (first 5 rows to capture multi-row headers)
    headers = []
    for row_idx in range(1, min(6, ws.max_row + 1)):
        row_data = []
        for col_idx in range(1, ws.max_column + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            row_data.append(cell.value)
        headers.append(row_data)
    sheet_info["header_rows"] = headers

    # Extract formulas
    formulas = []
    for row_idx in range(1, ws.max_row + 1):
        for col_idx in range(1, ws.max_column + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            if cell.data_type == "f" or (
                isinstance(cell.value, str) and cell.value.startswith("=")
            ):
                formulas.append({
                    "cell": f"{get_column_letter(col_idx)}{row_idx}",
                    "formula": cell.value,
                })
    sheet_info["formula_count"] = len(formulas)
    sheet_info["formulas"] = formulas

    # Extract column info
    columns = []
    # Try to find the actual header row (first non-empty row with multiple values)
    header_row_idx = None
    for row_idx in range(1, min(6, ws.max_row + 1)):
        non_empty = sum(
            1 for col_idx in range(1, ws.max_column + 1)
            if ws.cell(row=row_idx, column=col_idx).value is not None
        )
        if non_empty >= 3:
            header_row_idx = row_idx
            break

    if header_row_idx:
        for col_idx in range(1, ws.max_column + 1):
            cell = ws.cell(row=header_row_idx, column=col_idx)
            if cell.value is not None:
                columns.append({
                    "col_letter": get_column_letter(col_idx),
                    "col_index": col_idx,
                    "header": str(cell.value),
                })
    sheet_info["detected_header_row"] = header_row_idx
    sheet_info["columns"] = columns

    # Sample data rows (first 3 data rows after header)
    data_start = (header_row_idx or 1) + 1
    sample_rows = []
    for row_idx in range(data_start, min(data_start + 3, ws.max_row + 1)):
        row_data = {}
        for col_idx in range(1, ws.max_column + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            if cell.value is not None:
                col_letter = get_column_letter(col_idx)
                val = cell.value
                if isinstance(val, str) and val.startswith("="):
                    row_data[col_letter] = f"[FORMULA] {val}"
                else:
                    row_data[col_letter] = str(val)
        if row_data:
            sample_rows.append({"row": row_idx, "data": row_data})
    sheet_info["sample_data_rows"] = sample_rows

    return sheet_info


def main():
    if not os.path.exists(XLSX_PATH):
        print(f"ERROR: File not found: {XLSX_PATH}")
        return

    print(f"Reading: {XLSX_PATH}")
    # data_only=False to see formulas
    wb = load_workbook(XLSX_PATH, data_only=False)

    summary = {
        "source_file": XLSX_PATH,
        "account_code": "2801",
        "account_name": "其他非流动负债",
        "account_direction": "贷方/负债类",
        "formula_rule": "期末=期初+贷方-借方",
        "sheet_count": len(wb.sheetnames),
        "sheet_names": wb.sheetnames,
        "sheets": {},
    }

    total_formulas = 0
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        print(f"  Processing sheet: {sheet_name} ({ws.max_row}×{ws.max_column})")
        info = extract_sheet_structure(ws)
        summary["sheets"][sheet_name] = info
        total_formulas += info["formula_count"]
        print(f"    → {info['formula_count']} formulas, {ws.max_row} rows × {ws.max_column} cols")

    summary["total_formula_count"] = total_formulas

    # Confirm L7-1 审定表 structure
    l7_1_confirmed = False
    l7_2_confirmed = False
    for sn, info in summary["sheets"].items():
        if "审定" in sn or "L7-1" in sn:
            l7_1_confirmed = True
            summary["confirmation_l7_1"] = {
                "sheet_name": sn,
                "formula_count": info["formula_count"],
                "expected_formulas": 72,
                "match": info["formula_count"] == 72,
                "dimensions": f"{info['max_row']}×{info['max_column']}",
                "note": "审定表L7-1结构确认" if info["formula_count"] >= 50 else "公式数量可能不匹配",
            }
        if "明细" in sn or "L7-2" in sn:
            l7_2_confirmed = True
            summary["confirmation_l7_2"] = {
                "sheet_name": sn,
                "formula_count": info["formula_count"],
                "dimensions": f"{info['max_row']}×{info['max_column']}",
                "columns_count": len(info["columns"]),
                "note": "明细表L7-2结构确认",
            }

    if not l7_1_confirmed:
        summary["confirmation_l7_1"] = {"error": "未找到审定表L7-1 sheet"}
    if not l7_2_confirmed:
        summary["confirmation_l7_2"] = {"error": "未找到明细表L7-2 sheet"}

    # Write output
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\nOutput written to: {OUTPUT_PATH}")
    print(f"Total sheets: {summary['sheet_count']}")
    print(f"Total formulas: {total_formulas}")
    print(f"L7-1 confirmation: {summary.get('confirmation_l7_1', {})}")
    print(f"L7-2 confirmation: {summary.get('confirmation_l7_2', {})}")


if __name__ == "__main__":
    main()
