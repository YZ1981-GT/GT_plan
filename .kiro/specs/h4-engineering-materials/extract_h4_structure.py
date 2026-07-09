"""
Task 0.1: openpyxl脚本读取H4工程物资.xlsx全部13 sheet
提取：sheet名/列头/行数/公式单元格/合并区域/数据类型
产出：h4_structure_summary.json（权威列头+公式清单）
验证：13 sheet结构与本spec描述一致
"""

import json
import os
from pathlib import Path
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

# Source file path
XLSX_PATH = (
    r"D:\GT_plan\基础数据\致同通用审计程序及底稿模板（2025年修订）"
    r"\1.致同审计程序及底稿模板（2025年）\4.风险应对-实质性程序（D-N）"
    r"\H 固定资产循环\H4 工程物资.xlsx"
)

# Output path
OUTPUT_PATH = Path(__file__).parent / "h4_structure_summary.json"

# Expected 13 sheets from design.md
EXPECTED_SHEETS = [
    "Tab_Index",           # 底稿目录
    "Procedure_Table_H4A", # 实质性程序表
    "Adjudication_H4_1",   # 审定表
    "Disclosure_Listed",   # 附注上市
    "Disclosure_SOE",      # 附注国企
    "Detail_H4_2",         # 明细表
    "Adjustment_H4_3",     # 调整分录
    "Addition_Check_H4_4", # 增加检查
    "Disposal_Check_H4_5", # 减少检查
    "Stocktake_Check_H4_6",# 盘点检查
    "Impairment_H4_7",     # 减值测算
    "Recoverable_H4_8",    # 可收回金额
    "Related_Party_H4_9",  # 关联交易
]


def extract_sheet_structure(ws):
    """Extract structure info from a single worksheet."""
    sheet_info = {
        "sheet_name": ws.title,
        "max_row": ws.max_row,
        "max_column": ws.max_column,
        "dimensions": ws.dimensions,
        "column_headers": [],
        "formula_cells": [],
        "merged_areas": [],
        "data_types_sample": {},
    }

    # Extract column headers (first few rows, typically row 1-3 contain headers)
    headers_by_row = {}
    for row_idx in range(1, min(6, ws.max_row + 1)):
        row_headers = []
        for col_idx in range(1, ws.max_column + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            val = cell.value
            if val is not None:
                row_headers.append({
                    "col": col_idx,
                    "col_letter": get_column_letter(col_idx),
                    "value": str(val)[:100],  # Truncate long values
                })
        if row_headers:
            headers_by_row[f"row_{row_idx}"] = row_headers
    sheet_info["column_headers"] = headers_by_row

    # Extract formula cells
    formula_cells = []
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=ws.max_column):
        for cell in row:
            if cell.value and isinstance(cell.value, str) and cell.value.startswith("="):
                formula_cells.append({
                    "cell": f"{get_column_letter(cell.column)}{cell.row}",
                    "formula": str(cell.value)[:200],
                })
    sheet_info["formula_cells"] = formula_cells
    sheet_info["formula_count"] = len(formula_cells)

    # Extract merged areas
    merged = []
    for merge_range in ws.merged_cells.ranges:
        merged.append(str(merge_range))
    sheet_info["merged_areas"] = merged
    sheet_info["merged_count"] = len(merged)

    # Sample data types (first 10 data rows after headers)
    type_samples = {}
    for col_idx in range(1, min(ws.max_column + 1, 30)):
        col_letter = get_column_letter(col_idx)
        types_found = set()
        for row_idx in range(1, min(ws.max_row + 1, 20)):
            cell = ws.cell(row=row_idx, column=col_idx)
            if cell.value is not None:
                cell_type = type(cell.value).__name__
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    cell_type = "formula"
                types_found.add(cell_type)
        if types_found:
            type_samples[col_letter] = list(types_found)
    sheet_info["data_types_sample"] = type_samples

    return sheet_info


def main():
    print(f"Loading workbook: {XLSX_PATH}")
    if not os.path.exists(XLSX_PATH):
        raise FileNotFoundError(f"File not found: {XLSX_PATH}")

    # Load with data_only=False to preserve formulas
    wb = load_workbook(XLSX_PATH, data_only=False, read_only=False)

    print(f"Sheet count: {len(wb.sheetnames)}")
    print(f"Sheet names: {wb.sheetnames}")

    result = {
        "source_file": XLSX_PATH,
        "sheet_count": len(wb.sheetnames),
        "sheet_names": wb.sheetnames,
        "sheets": {},
        "verification": {},
    }

    # Extract each sheet
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        print(f"\nProcessing: {sheet_name} ({ws.max_row} rows × {ws.max_column} cols)")
        sheet_data = extract_sheet_structure(ws)
        result["sheets"][sheet_name] = sheet_data

    # Verification: compare with expected 13 sheets
    actual_names = wb.sheetnames
    verification = {
        "expected_count": 13,
        "actual_count": len(actual_names),
        "count_match": len(actual_names) == 13,
        "actual_sheet_names": actual_names,
        "expected_sheet_design_names": EXPECTED_SHEETS,
        "mapping_attempt": {},
    }

    # Try to map actual sheet names to design names
    # The actual xlsx uses Chinese names, design uses English aliases
    print("\n\n=== VERIFICATION ===")
    print(f"Expected: 13 sheets")
    print(f"Actual: {len(actual_names)} sheets")
    print(f"Match: {len(actual_names) == 13}")
    print(f"\nActual sheet names:")
    for i, name in enumerate(actual_names, 1):
        ws = wb[name]
        print(f"  {i:2d}. {name} ({ws.max_row}行 × {ws.max_column}列)")

    # Summary statistics
    total_formulas = sum(
        result["sheets"][s]["formula_count"] for s in wb.sheetnames
    )
    total_merged = sum(
        result["sheets"][s]["merged_count"] for s in wb.sheetnames
    )
    print(f"\nTotal formulas: {total_formulas}")
    print(f"Total merged areas: {total_merged}")

    verification["total_formulas"] = total_formulas
    verification["total_merged_areas"] = total_merged

    result["verification"] = verification

    # Write output
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Output written to: {OUTPUT_PATH}")
    print(f"   File size: {OUTPUT_PATH.stat().st_size:,} bytes")

    wb.close()
    return result


if __name__ == "__main__":
    main()
