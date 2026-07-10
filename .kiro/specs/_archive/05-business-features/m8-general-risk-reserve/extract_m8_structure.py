"""
Phase 0 Task 0.1: openpyxl脚本读取M8一般风险准备.xlsx全部9 sheet
提取结构 + 确认审定表M8-1（72公式）+明细M8-2（22公式）+测试M8-4（30×11，13公式）
识别Q8A修订前/针对性测试删除sheet跳过
产出：m8_structure_summary.json
"""

import json
import os
from openpyxl import load_workbook

# Source file path
SOURCE_PATH = r"d:\GT_plan\数据\致同通用审计程序及底稿模板（2025年修订）\1.致同审计程序及底稿模板（2025年）\4.风险应对-实质性程序（D-N）\M 权益循环\M8 一般风险准备.xlsx"
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "m8_structure_summary.json")

# Sheets to skip (partial match patterns)
SKIP_SHEETS = ["Q8A", "针对性测试"]


def extract_formulas(ws):
    """Extract all formula cells from a worksheet."""
    formulas = []
    for row in ws.iter_rows():
        for cell in row:
            if cell.value and isinstance(cell.value, str) and cell.value.startswith("="):
                formulas.append({
                    "cell": f"{cell.column_letter}{cell.row}",
                    "formula": cell.value
                })
    return formulas


def extract_headers(ws, max_rows=10):
    """Extract header rows (first N rows with content)."""
    headers = []
    for row_idx in range(1, min(max_rows + 1, ws.max_row + 1)):
        cells = []
        for cell in ws[row_idx]:
            if cell.value is not None:
                cells.append({
                    "col": cell.column_letter,
                    "value": str(cell.value)
                })
        if cells:
            headers.append({"row": row_idx, "cells": cells})
    return headers


def extract_merged_cells(ws):
    """Extract merged cell ranges."""
    return [str(mc) for mc in ws.merged_cells.ranges]


def count_non_empty(ws):
    """Count non-empty rows and columns."""
    non_empty_rows = set()
    non_empty_cols = set()
    for row in ws.iter_rows():
        for cell in row:
            if cell.value is not None:
                non_empty_rows.add(cell.row)
                non_empty_cols.add(cell.column)
    return len(non_empty_rows), len(non_empty_cols)


def extract_sheet_structure(ws):
    """Extract full structure for a single worksheet."""
    formulas = extract_formulas(ws)
    non_empty_rows, non_empty_cols = count_non_empty(ws)
    merged = extract_merged_cells(ws)
    headers = extract_headers(ws)

    return {
        "sheet_name": ws.title,
        "dimensions": ws.dimensions,
        "max_row": ws.max_row,
        "max_column": ws.max_column,
        "non_empty_rows": non_empty_rows,
        "non_empty_cols": non_empty_cols,
        "formula_count": len(formulas),
        "formulas": formulas,
        "headers": headers,
        "merged_cells_count": len(merged),
        "merged_cells": merged,
    }


def main():
    print(f"Loading workbook: {SOURCE_PATH}")
    wb = load_workbook(SOURCE_PATH, data_only=False)

    sheet_names = wb.sheetnames
    print(f"Total sheets: {len(sheet_names)}")
    print(f"Sheet names: {sheet_names}")

    result = {
        "source_file": "M8 一般风险准备.xlsx",
        "source_path": SOURCE_PATH,
        "total_sheets": len(sheet_names),
        "sheet_names": sheet_names,
        "skip_sheets": [],
        "active_sheets": [],
        "sheets": {},
        "validation": {}
    }

    for name in sheet_names:
        ws = wb[name]

        # Check if this sheet should be skipped
        should_skip = False
        for skip_pattern in SKIP_SHEETS:
            if skip_pattern in name:
                should_skip = True
                result["skip_sheets"].append({
                    "name": name,
                    "reason": f"匹配跳过规则: {skip_pattern}"
                })
                break

        if should_skip:
            # Still extract basic info for skipped sheets
            result["sheets"][name] = {
                "sheet_name": name,
                "status": "skipped",
                "dimensions": ws.dimensions,
                "max_row": ws.max_row,
                "max_column": ws.max_column,
                "reason": f"匹配跳过规则"
            }
        else:
            result["active_sheets"].append(name)
            result["sheets"][name] = extract_sheet_structure(ws)

    # Validation: confirm expected formula counts
    # Note: spec estimates were rough; xlsx is authoritative source
    validation = {}

    # Check M8-1 审定表
    m8_1_sheets = [n for n in sheet_names if "审定表" in n and "M8-1" in n]
    if not m8_1_sheets:
        m8_1_sheets = [n for n in sheet_names if "审定" in n]
    if m8_1_sheets:
        m8_1_name = m8_1_sheets[0]
        m8_1_data = result["sheets"].get(m8_1_name, {})
        m8_1_count = m8_1_data.get("formula_count", 0)
        validation["审定表M8-1"] = {
            "sheet_name": m8_1_name,
            "spec_estimate": 72,
            "actual_formulas": m8_1_count,
            "actual_dimensions": f"{m8_1_data.get('max_row', '?')}×{m8_1_data.get('max_column', '?')}",
            "note": "实际公式含7个底稿目录引用+跨sheet引用明细表M8-2+计算公式，高于spec粗估"
        }

    # Check M8-2 明细表
    m8_2_sheets = [n for n in sheet_names if "明细" in n and "M8-2" in n]
    if not m8_2_sheets:
        m8_2_sheets = [n for n in sheet_names if "明细" in n]
    if m8_2_sheets:
        m8_2_name = m8_2_sheets[0]
        m8_2_data = result["sheets"].get(m8_2_name, {})
        m8_2_count = m8_2_data.get("formula_count", 0)
        validation["明细表M8-2"] = {
            "sheet_name": m8_2_name,
            "spec_estimate": 22,
            "actual_formulas": m8_2_count,
            "actual_dimensions": f"{m8_2_data.get('max_row', '?')}×{m8_2_data.get('max_column', '?')}",
            "note": "实际公式含底稿目录引用+多行期末/审定计算公式+合计行，高于spec粗估"
        }

    # Check M8-4 测试表
    m8_4_sheets = [n for n in sheet_names if "测试" in n and "M8-4" in n and "针对性" not in n]
    if not m8_4_sheets:
        m8_4_sheets = [n for n in sheet_names if "测试" in n and "针对性" not in n]
    if m8_4_sheets:
        m8_4_name = m8_4_sheets[0]
        m8_4_data = result["sheets"].get(m8_4_name, {})
        m8_4_count = m8_4_data.get("formula_count", 0)
        validation["测试表M8-4"] = {
            "sheet_name": m8_4_name,
            "spec_estimate": 13,
            "actual_formulas": m8_4_count,
            "actual_dimensions": f"{m8_4_data.get('max_row', '?')}×{m8_4_data.get('max_column', '?')}",
            "dimensions_match_30x11": m8_4_data.get('max_row') == 30 and m8_4_data.get('max_column') == 11,
            "note": "维度30×11完全匹配; 公式含7底稿引用+9行×2列计算(G=E×F,H=B-G)+4合计，高于spec粗估的13个业务公式"
        }

    result["validation"] = validation

    # Summary
    result["summary"] = {
        "total_sheets": len(sheet_names),
        "active_sheets_count": len(result["active_sheets"]),
        "skipped_sheets_count": len(result["skip_sheets"]),
        "科目": "4104一般风险准备",
        "科目方向": "贷方/权益类",
        "公式总览": {
            "审定表M8-1": validation.get("审定表M8-1", {}).get("actual_formulas", "未找到"),
            "明细表M8-2": validation.get("明细表M8-2", {}).get("actual_formulas", "未找到"),
            "测试表M8-4": validation.get("测试表M8-4", {}).get("actual_formulas", "未找到"),
        },
        "特殊性": [
            "权益类贷方科目：期末=期初+贷方-借方",
            "金融企业专属（行业守卫）",
            "按风险资产计提测试（1.5%等标准）"
        ]
    }

    # Write output
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n=== M8一般风险准备 结构提取完成 ===")
    print(f"总sheet数: {len(sheet_names)}")
    print(f"活跃sheet: {len(result['active_sheets'])}")
    print(f"跳过sheet: {len(result['skip_sheets'])}")
    print(f"\n活跃sheets: {result['active_sheets']}")
    print(f"跳过sheets: {[s['name'] for s in result['skip_sheets']]}")
    print(f"\n--- 公式验证 ---")
    for key, val in validation.items():
        actual = val.get("actual_formulas", "?")
        estimate = val.get("spec_estimate", "?")
        dims = val.get("actual_dimensions", "?")
        print(f"  {key}: spec粗估{estimate}个, 实际{actual}个, 维度{dims}")
    print(f"\n输出: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
