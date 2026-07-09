"""
Phase0 双源输入 - Task 0.1
openpyxl脚本读取K3其他应付款.xlsx全部11 sheet
产出：k3_structure_summary.json（确认K3-1 50公式/K3-2 19公式/K3-4 8公式）

科目：2241其他应付款（贷方/负债类）
期末=期初+贷方-借方（与资产类相反）
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

# K3 xlsx 路径
XLSX_PATH = Path(
    r"d:\GT_plan\基础数据\致同通用审计程序及底稿模板（2025年修订）"
    r"\1.致同审计程序及底稿模板（2025年）"
    r"\4.风险应对-实质性程序（D-N）"
    r"\K 管理循环"
    r"\K3 其他应付款.xlsx"
)

OUTPUT_PATH = Path(r"d:\GT_plan\.kiro\specs\k3-other-payables\k3_structure_summary.json")


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

    # Extract column headers (first few rows)
    header_rows = min(4, ws.max_row)
    for row_idx in range(1, header_rows + 1):
        row_headers = []
        for col_idx in range(1, ws.max_column + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            val = cell.value
            if val is not None:
                row_headers.append({
                    "col": get_column_letter(col_idx),
                    "value": str(val)[:100],
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
                    "formula": cell.value[:150],
                })

    sheet_info["formula_count"] = len(sheet_info["formulas"])

    # Sample data rows (rows after headers for context)
    sample_start = min(5, ws.max_row)
    sample_end = min(10, ws.max_row)
    for row_idx in range(sample_start, sample_end + 1):
        row_data = []
        for col_idx in range(1, min(ws.max_column + 1, 15)):  # cap at 15 cols
            cell = ws.cell(row=row_idx, column=col_idx)
            val = cell.value
            if val is not None:
                row_data.append({
                    "col": get_column_letter(col_idx),
                    "value": str(val)[:80],
                })
        if row_data:
            sheet_info["sample_data_rows"].append({
                "row": row_idx,
                "cells": row_data
            })

    return sheet_info


def find_sheet_by_prefix(formula_by_sheet, prefix):
    """Find sheet formula count by prefix match."""
    for key, count in formula_by_sheet.items():
        if prefix in key:
            return count
    return 0


def main():
    if not XLSX_PATH.exists():
        print(f"ERROR: File not found: {XLSX_PATH}")
        sys.exit(1)

    print(f"Loading: {XLSX_PATH.name}")
    wb = load_workbook(XLSX_PATH, data_only=False)  # data_only=False to preserve formulas

    print(f"Sheet count: {len(wb.sheetnames)}")
    print(f"Sheet names:")
    for i, name in enumerate(wb.sheetnames, 1):
        print(f"  {i:2d}. {name}")

    summary = {
        "file": str(XLSX_PATH.name),
        "subject": "2241 其他应付款（贷方/负债类）",
        "formula_direction": "期末=期初+贷方-借方（负债类，与资产类相反）",
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
    k3_1_formulas = find_sheet_by_prefix(formula_by_sheet, "K3-1")
    k3_2_formulas = find_sheet_by_prefix(formula_by_sheet, "K3-2")
    k3_4_formulas = find_sheet_by_prefix(formula_by_sheet, "K3-4")

    summary["key_metrics"] = {
        "total_formulas": total_formulas,
        "formula_by_sheet": formula_by_sheet,
        "validation": {
            "K3-1_formulas": k3_1_formulas,
            "K3-1_target": "~50",
            "K3-2_formulas": k3_2_formulas,
            "K3-2_target": "~19",
            "K3-4_formulas": k3_4_formulas,
            "K3-4_target": "~8",
            "total_formulas": total_formulas,
            "total_target": "~80+",
        },
        "expected_11_sheets": {
            "Tab_Index": "底稿目录",
            "K3A程序表": "其他应付款实质性程序表",
            "K3-1审定表": "审定表（负债类，50公式）",
            "K3-2明细表": "明细表（27列3区段+账龄，19公式）",
            "K3-3调整分录": "调整分录汇总",
            "K3-4大额分析": "大额其他应付款分析表（8公式）",
            "K3-5长期挂账": "长期挂账检查表",
            "K3-6关联方": "关联方及交易检查表",
            "K3-7综合检查": "其他应付款检查表（含反向截止）",
            "附注上市": "附注披露信息（上市公司）",
            "附注国企": "附注披露信息（国企）",
        },
    }

    # Write output
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*50}")
    print(f"=== K3 其他应付款 结构分析汇总 ===")
    print(f"{'='*50}")
    print(f"科目: 2241 其他应付款（贷方/负债类）")
    print(f"方向: 期末=期初+贷方-借方")
    print(f"Sheet数: {len(wb.sheetnames)}")
    print(f"Total formulas: {total_formulas} (target: ~80+)")
    print(f"  K3-1 审定表 formulas: {k3_1_formulas} (target: ~50)")
    print(f"  K3-2 明细表 formulas: {k3_2_formulas} (target: ~19)")
    print(f"  K3-4 大额分析 formulas: {k3_4_formulas} (target: ~8)")
    print(f"\nOutput: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
