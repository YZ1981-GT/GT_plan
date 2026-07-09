"""
Phase0 双源输入 - Task 0.1
openpyxl脚本读取K2其他流动资产.xlsx全部10 sheet
产出：k2_structure_summary.json
"""
import json
import sys
from pathlib import Path

try:
    from openpyxl import load_workbook
    from openpyxl.utils import get_column_letter
except ImportError:
    print("ERROR: openpyxl not installed. Run: pip install openpyxl")
    sys.exit(1)

# K2 xlsx 路径
XLSX_PATH = Path(r"d:\GT_plan\基础数据\致同通用审计程序及底稿模板（2025年修订）\1.致同审计程序及底稿模板（2025年）\4.风险应对-实质性程序（D-N）\K 管理循环\K2 其他流动资产.xlsx")

OUTPUT_PATH = Path(r"d:\GT_plan\.kiro\specs\k2-other-current-assets\k2_structure_summary.json")


def extract_sheet_structure(ws):
    """Extract structure from a single worksheet."""
    sheet_info = {
        "title": ws.title,
        "dimensions": ws.dimensions,
        "max_row": ws.max_row,
        "max_column": ws.max_column,
        "merged_cells": [str(m) for m in ws.merged_cells.ranges],
        "merged_cell_count": len(ws.merged_cells.ranges),
        "column_headers": [],
        "formulas": [],
        "formula_count": 0,
        "sample_data_rows": [],
    }

    # Extract column headers (first few rows typically)
    header_rows = min(3, ws.max_row)
    for row_idx in range(1, header_rows + 1):
        row_headers = []
        for col_idx in range(1, ws.max_column + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            val = cell.value
            if val is not None:
                row_headers.append({
                    "col": get_column_letter(col_idx),
                    "value": str(val)[:80],
                })
        if row_headers:
            sheet_info["column_headers"].append({
                "row": row_idx,
                "cells": row_headers
            })

    # Extract all formulas
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=ws.max_column):
        for cell in row:
            if cell.value and isinstance(cell.value, str) and cell.value.startswith("="):
                sheet_info["formulas"].append({
                    "cell": f"{get_column_letter(cell.column)}{cell.row}",
                    "formula": cell.value[:120],
                })

    sheet_info["formula_count"] = len(sheet_info["formulas"])

    # Sample data rows (rows 4-8 for context)
    sample_start = min(4, ws.max_row)
    sample_end = min(8, ws.max_row)
    for row_idx in range(sample_start, sample_end + 1):
        row_data = []
        for col_idx in range(1, min(ws.max_column + 1, 15)):  # cap at 15 cols for readability
            cell = ws.cell(row=row_idx, column=col_idx)
            val = cell.value
            if val is not None:
                row_data.append({
                    "col": get_column_letter(col_idx),
                    "value": str(val)[:60],
                })
        if row_data:
            sheet_info["sample_data_rows"].append({
                "row": row_idx,
                "cells": row_data
            })

    return sheet_info


def main():
    if not XLSX_PATH.exists():
        print(f"ERROR: File not found: {XLSX_PATH}")
        sys.exit(1)

    print(f"Loading: {XLSX_PATH.name}")
    wb = load_workbook(XLSX_PATH, data_only=False)  # data_only=False to get formulas

    print(f"Sheet count: {len(wb.sheetnames)}")
    print(f"Sheet names: {wb.sheetnames}")

    summary = {
        "file": str(XLSX_PATH.name),
        "sheet_count": len(wb.sheetnames),
        "sheet_names": wb.sheetnames,
        "sheets": [],
        "key_metrics": {},
    }

    total_formulas = 0
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        info = extract_sheet_structure(ws)
        summary["sheets"].append(info)
        total_formulas += info["formula_count"]
        print(f"  [{sheet_name}] rows={info['max_row']}, cols={info['max_column']}, "
              f"formulas={info['formula_count']}, merged={info['merged_cell_count']}")

    # Key metrics validation
    formula_by_sheet = {s["title"]: s["formula_count"] for s in summary["sheets"]}
    summary["key_metrics"] = {
        "total_formulas": total_formulas,
        "formula_by_sheet": formula_by_sheet,
        "validation": {
            "K2-1_formulas": formula_by_sheet.get("K2-1 审定表", formula_by_sheet.get(next((k for k in formula_by_sheet if "K2-1" in k), ""), 0)),
            "K2-4_formulas": formula_by_sheet.get("K2-4 合同取得成本明细表", formula_by_sheet.get(next((k for k in formula_by_sheet if "K2-4" in k), ""), 0)),
            "K2-5_formulas": formula_by_sheet.get("K2-5 摊销测算表", formula_by_sheet.get(next((k for k in formula_by_sheet if "K2-5" in k), ""), 0)),
        },
    }

    # Write output
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n=== Key Metrics ===")
    print(f"Total formulas: {total_formulas}")
    print(f"K2-1 formulas: {summary['key_metrics']['validation']['K2-1_formulas']} (target: ~85)")
    print(f"K2-4 formulas: {summary['key_metrics']['validation']['K2-4_formulas']} (target: ~57)")
    print(f"K2-5 formulas: {summary['key_metrics']['validation']['K2-5_formulas']} (target: ~37)")
    print(f"\nOutput written to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
