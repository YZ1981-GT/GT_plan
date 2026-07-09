"""
I1 无形资产、累计摊销及减值准备.xlsx 结构提取脚本

提取每个sheet的：
- sheet名
- 列头（前5行）
- 行数/列数
- 公式单元格
- 合并区域
- 数据类型
- 列宽

产出: i1_structure_summary.json
"""

import json
import os
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

XLSX_PATH = r"d:\GT_plan\基础数据\致同通用审计程序及底稿模板（2025年修订）\1.致同审计程序及底稿模板（2025年）\4.风险应对-实质性程序（D-N）\I 无形资产循环\I1 无形资产、累计摊销及减值准备.xlsx"
OUTPUT_PATH = r"d:\GT_plan\.kiro\specs\i1-intangible-assets\i1_structure_summary.json"


def extract_sheet_info(ws):
    """Extract structure information from a worksheet."""
    info = {
        "sheet_name": ws.title,
        "dimensions": ws.dimensions,
        "max_row": ws.max_row,
        "max_column": ws.max_column,
        "merged_cells": [str(m) for m in ws.merged_cells.ranges],
        "headers": [],
        "column_widths": {},
        "formula_cells": [],
        "data_types": {},
    }

    # Extract first 5 rows as headers
    for row_idx in range(1, min(6, ws.max_row + 1)):
        row_data = []
        for col_idx in range(1, ws.max_column + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            val = cell.value
            if val is not None and str(val).startswith("="):
                row_data.append(str(val))
            elif val is not None:
                row_data.append(str(val))
            else:
                row_data.append(None)
        info["headers"].append(row_data)

    # Column widths
    for col_idx in range(1, ws.max_column + 1):
        col_letter = get_column_letter(col_idx)
        if col_letter in ws.column_dimensions:
            info["column_widths"][col_letter] = ws.column_dimensions[col_letter].width

    # Formula cells and data types
    type_counts = {}
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=ws.max_column):
        for cell in row:
            if cell.value is not None:
                # Track data types
                dt = cell.data_type
                type_counts[dt] = type_counts.get(dt, 0) + 1

                # Track formula cells
                if cell.data_type == "f":
                    info["formula_cells"].append({
                        "cell": f"{get_column_letter(cell.column)}{cell.row}",
                        "formula": str(cell.value),
                    })

    info["data_types"] = type_counts
    info["formula_count"] = len(info["formula_cells"])

    return info


def main():
    print(f"Loading workbook: {XLSX_PATH}")
    wb = load_workbook(XLSX_PATH, data_only=False)

    result = {
        "file_path": XLSX_PATH,
        "total_sheets": len(wb.sheetnames),
        "sheet_names": wb.sheetnames,
        "sheets": {},
    }

    for sheet_name in wb.sheetnames:
        print(f"  Processing: {sheet_name}")
        ws = wb[sheet_name]
        sheet_info = extract_sheet_info(ws)
        result["sheets"][sheet_name] = sheet_info

    # Summary comparison with spec
    spec_sheets = {
        "Tab_Index": "底稿目录",
        "Procedure_Table_I1A": "I1A",
        "Adjudication_I1": "审定表I1",
        "Disclosure_Listed": "上市公司",
        "Disclosure_SOE": "国有企业",
        "Detail_I1_2": "明细表I1-2",
        "Adjustment_I1_3": "调整分录",
        "Policy_Check_I1_4": "I1-4",
        "Addition_Check_I1_5": "I1-5",
        "Disposal_Check_I1_6": "I1-6",
        "UsefulLife_Check_I1_7": "I1-7",
        "Title_Check_I1_8": "I1-8",
        "Amortization_Alloc_I1_9": "I1-9",
        "Amortization_NoImpair_I1_10": "I1-10",
        "Amortization_WithImpair_I1_11": "I1-11",
        "Impairment_Test_I1_12": "I1-12",
        "Recoverable_Test_I1_13": "I1-13",
    }

    result["spec_validation"] = {
        "expected_sheet_count": 18,
        "actual_sheet_count": len(wb.sheetnames),
        "sheet_count_match": len(wb.sheetnames) >= 17,
        "spec_sheet_mapping": {},
    }

    # Try to map spec names to actual sheet names
    for spec_key, keyword in spec_sheets.items():
        matched = None
        for actual_name in wb.sheetnames:
            if keyword in actual_name:
                matched = actual_name
                break
        result["spec_validation"]["spec_sheet_mapping"][spec_key] = {
            "keyword": keyword,
            "matched_sheet": matched,
            "found": matched is not None,
        }

    # Write output
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\nOutput written to: {OUTPUT_PATH}")
    print(f"Total sheets: {len(wb.sheetnames)}")
    print(f"Sheet names: {wb.sheetnames}")

    # Print summary
    total_formulas = sum(
        result["sheets"][s]["formula_count"] for s in wb.sheetnames
    )
    print(f"Total formulas across all sheets: {total_formulas}")

    # Validation summary
    unmatched = [
        k for k, v in result["spec_validation"]["spec_sheet_mapping"].items()
        if not v["found"]
    ]
    if unmatched:
        print(f"\n⚠️  Unmatched spec sheets: {unmatched}")
    else:
        print("\n✅ All spec sheets matched to actual xlsx sheets")


if __name__ == "__main__":
    main()
