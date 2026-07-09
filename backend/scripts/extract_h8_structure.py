"""
Phase 0 Task 0.1: openpyxl脚本读取H8使用权资产.xlsx全部20 sheet
提取：sheet名/列头/行数/公式单元格/合并区域/数据类型
产出：h8_structure_summary.json（权威列头+公式清单）
验证：20 sheet结构与spec描述一致，含H8-6/H8-8各2分支
"""

import json
import os
from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter

# H8使用权资产.xlsx路径
XLSX_PATH = Path(
    r"d:\GT_plan\基础数据\致同通用审计程序及底稿模板（2025年修订）"
    r"\1.致同审计程序及底稿模板（2025年）"
    r"\4.风险应对-实质性程序（D-N）"
    r"\H 固定资产循环"
    r"\H8 使用权资产.xlsx"
)

OUTPUT_PATH = Path(r"d:\GT_plan\.kiro\specs\h8-right-of-use-assets\h8_structure_summary.json")

# spec中定义的20个有效sheet（按预期）
EXPECTED_SHEETS = [
    "Tab_Index",
    "Procedure_Table_H8A",
    "Adjudication_H8_1",
    "Disclosure_Listed",
    "Disclosure_SOE",
    "Detail_H8_2",
    "Adjustment_H8_3",
    "Lease_Identification_H8_4",
    "Lease_Term_H8_5",
    "Measurement_Annual_H8_6",      # H8-6 分支A: 按年计量
    "Measurement_Monthly_H8_6",     # H8-6 分支B: 按月计量
    "Lease_Modification_H8_7",
    "Depreciation_NoImpair_H8_8",   # H8-8 分支A: 不含减值
    "Depreciation_WithImpair_H8_8", # H8-8 分支B: 含减值
    "Depreciation_Alloc_H8_9",
    "Impairment_H8_10",
    "Recoverable_H8_11",
    "Disposal_Check_H8_12",
    "Simplified_Check_H8_13",
    "Related_Party_H8_14",
]

# H8-6/H8-8 双分支定义（用于验证）
BRANCH_DEFINITIONS = {
    "H8-6": {
        "description": "使用权资产初始及后续计量",
        "branches": {
            "Annual": {
                "glossary_name": "Measurement_Annual_H8_6",
                "description": "按年计量",
                "expected_rows": 59,
                "expected_cols": 13,
            },
            "Monthly": {
                "glossary_name": "Measurement_Monthly_H8_6",
                "description": "按月计量",
                "expected_rows": 361,
                "expected_cols": 16,
            },
        },
    },
    "H8-8": {
        "description": "折旧测算表",
        "branches": {
            "NoImpair": {
                "glossary_name": "Depreciation_NoImpair_H8_8",
                "description": "不含减值",
                "expected_rows": 51,
                "expected_cols": 25,
            },
            "WithImpair": {
                "glossary_name": "Depreciation_WithImpair_H8_8",
                "description": "含减值",
                "expected_rows": 49,
                "expected_cols": 27,
            },
        },
    },
}


def extract_sheet_structure(ws, sheet_name: str) -> dict:
    """提取单个sheet的完整结构信息"""
    result = {
        "sheet_name": sheet_name,
        "max_row": ws.max_row,
        "max_column": ws.max_column,
        "column_count": ws.max_column,
        "merged_ranges": [],
        "headers": [],
        "formula_cells": [],
        "data_types": {},
        "sample_data": [],
    }

    # 合并区域
    for merge in ws.merged_cells.ranges:
        result["merged_ranges"].append(str(merge))

    # 提取列头（前3行，通常为表头区域）
    header_rows = []
    for row_idx in range(1, min(4, ws.max_row + 1)):
        row_data = []
        for col_idx in range(1, ws.max_column + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            val = cell.value
            if val is not None:
                row_data.append({
                    "col": get_column_letter(col_idx),
                    "col_idx": col_idx,
                    "value": str(val)[:200],
                })
        if row_data:
            header_rows.append({"row": row_idx, "cells": row_data})
    result["headers"] = header_rows

    # 扫描公式单元格和数据类型统计
    type_counts = {}
    formula_count = 0
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=ws.max_column):
        for cell in row:
            dt = cell.data_type
            type_counts[dt] = type_counts.get(dt, 0) + 1

            if cell.data_type == "f" or (
                isinstance(cell.value, str) and cell.value.startswith("=")
            ):
                formula_count += 1
                if len(result["formula_cells"]) < 100:
                    result["formula_cells"].append({
                        "cell": f"{get_column_letter(cell.column)}{cell.row}",
                        "formula": str(cell.value)[:300],
                    })

    result["data_types"] = type_counts
    result["formula_count"] = formula_count

    # 样本数据（取前5行非空数据行）
    data_start_row = 4
    sample_rows_collected = 0
    for row_idx in range(data_start_row, min(data_start_row + 10, ws.max_row + 1)):
        row_data = []
        has_data = False
        for col_idx in range(1, min(ws.max_column + 1, 20)):
            cell = ws.cell(row=row_idx, column=col_idx)
            val = cell.value
            if val is not None:
                has_data = True
                row_data.append({
                    "col": get_column_letter(col_idx),
                    "value": str(val)[:100],
                    "type": cell.data_type,
                })
        if has_data and sample_rows_collected < 5:
            result["sample_data"].append({"row": row_idx, "cells": row_data})
            sample_rows_collected += 1

    return result


def validate_branches(summary: dict) -> dict:
    """验证H8-6和H8-8的双分支结构"""
    validation = {
        "h8_6_branches": {"found": False, "annual": None, "monthly": None},
        "h8_8_branches": {"found": False, "no_impair": None, "with_impair": None},
    }

    sheet_map = {s["sheet_name"]: s for s in summary["sheets"]}
    actual_names = summary["sheet_names"]

    # 检测H8-6双分支（按年/按月）
    # 查找包含"计量"或"H8-6"关键词的sheet
    h8_6_sheets = []
    h8_8_sheets = []
    for name in actual_names:
        name_lower = name.lower()
        # H8-6: 按年/按月计量
        if "计量" in name or ("h8-6" in name_lower) or ("初始" in name and "后续" in name):
            h8_6_sheets.append(name)
        # H8-8: 折旧/含减值/不含减值
        if "折旧" in name and ("减值" in name or "h8-8" in name_lower):
            h8_8_sheets.append(name)
        # 也匹配英文缩写模式
        if "annual" in name_lower or "monthly" in name_lower:
            h8_6_sheets.append(name)
        if "noimpair" in name_lower or "withimpair" in name_lower:
            h8_8_sheets.append(name)

    # 去重
    h8_6_sheets = list(dict.fromkeys(h8_6_sheets))
    h8_8_sheets = list(dict.fromkeys(h8_8_sheets))

    validation["h8_6_branches"] = {
        "found": len(h8_6_sheets) >= 2,
        "count": len(h8_6_sheets),
        "sheet_names": h8_6_sheets,
        "expected_count": 2,
        "description": "H8-6 按年计量/按月计量 双分支",
    }

    validation["h8_8_branches"] = {
        "found": len(h8_8_sheets) >= 2,
        "count": len(h8_8_sheets),
        "sheet_names": h8_8_sheets,
        "expected_count": 2,
        "description": "H8-8 不含减值/含减值 双分支",
    }

    # 详细的分支结构匹配
    for branch_key, branch_def in BRANCH_DEFINITIONS.items():
        branch_info = {
            "key": branch_key,
            "description": branch_def["description"],
            "branches_found": [],
        }
        for variant_name, variant_def in branch_def["branches"].items():
            # 在实际sheet列表中模糊匹配
            matched_sheet = None
            matched_info = None
            for actual_name in actual_names:
                # 匹配关键词
                if branch_key == "H8-6":
                    if variant_name == "Annual" and ("按年" in actual_name or "annual" in actual_name.lower()):
                        matched_sheet = actual_name
                    elif variant_name == "Monthly" and ("按月" in actual_name or "monthly" in actual_name.lower()):
                        matched_sheet = actual_name
                elif branch_key == "H8-8":
                    if variant_name == "NoImpair" and ("不含减值" in actual_name or "noimpair" in actual_name.lower()):
                        matched_sheet = actual_name
                    elif variant_name == "WithImpair" and (
                        ("含减值" in actual_name and "不含" not in actual_name)
                        or "withimpair" in actual_name.lower()
                    ):
                        matched_sheet = actual_name

            if matched_sheet and matched_sheet in sheet_map:
                s = sheet_map[matched_sheet]
                matched_info = {
                    "variant": variant_name,
                    "glossary_name": variant_def["glossary_name"],
                    "actual_sheet_name": matched_sheet,
                    "actual_rows": s["max_row"],
                    "actual_cols": s["max_column"],
                    "expected_rows": variant_def["expected_rows"],
                    "expected_cols": variant_def["expected_cols"],
                    "rows_match": s["max_row"] == variant_def["expected_rows"],
                    "cols_match": s["max_column"] == variant_def["expected_cols"],
                }
            else:
                matched_info = {
                    "variant": variant_name,
                    "glossary_name": variant_def["glossary_name"],
                    "actual_sheet_name": None,
                    "note": "未能通过关键词匹配到实际sheet",
                }
            branch_info["branches_found"].append(matched_info)

        validation[f"{branch_key}_detail"] = branch_info

    return validation


def main():
    print(f"Reading: {XLSX_PATH}")
    if not XLSX_PATH.exists():
        print(f"ERROR: File not found: {XLSX_PATH}")
        return

    # data_only=False 保留公式；read_only=False 读取合并区域
    wb = openpyxl.load_workbook(str(XLSX_PATH), data_only=False, read_only=False)

    sheet_names = wb.sheetnames
    print(f"Total sheets found: {len(sheet_names)}")
    print(f"Sheet names: {sheet_names}")

    summary = {
        "source_file": str(XLSX_PATH),
        "total_sheets": len(sheet_names),
        "sheet_names": sheet_names,
        "expected_sheet_count": 20,
        "sheets_match_expected": len(sheet_names) == 20,
        "sheets": [],
    }

    for idx, name in enumerate(sheet_names):
        print(f"  [{idx+1}/{len(sheet_names)}] Processing: {name}")
        ws = wb[name]
        sheet_info = extract_sheet_structure(ws, name)
        summary["sheets"].append(sheet_info)

    # 生成映射表（spec glossary name → actual sheet name）
    print("\n--- Sheet Name Mapping (spec → actual) ---")
    summary["sheet_name_mapping"] = {}
    for i, actual_name in enumerate(sheet_names):
        expected_name = EXPECTED_SHEETS[i] if i < len(EXPECTED_SHEETS) else f"EXTRA_{i}"
        summary["sheet_name_mapping"][expected_name] = actual_name
        match_mark = "✓" if i < len(EXPECTED_SHEETS) else "⚠ EXTRA"
        print(f"  {match_mark} {expected_name:40s} → {actual_name}")

    # 验证H8-6/H8-8双分支
    print("\n--- H8-6/H8-8 Branch Validation ---")
    branch_validation = validate_branches(summary)
    summary["branch_validation"] = branch_validation

    h8_6_ok = branch_validation["h8_6_branches"]["found"]
    h8_8_ok = branch_validation["h8_8_branches"]["found"]
    print(f"  H8-6 (按年/按月): {'✓ PASS' if h8_6_ok else '✗ FAIL'} "
          f"(found {branch_validation['h8_6_branches']['count']} branches)")
    if branch_validation["h8_6_branches"]["sheet_names"]:
        for sn in branch_validation["h8_6_branches"]["sheet_names"]:
            print(f"    - {sn}")
    print(f"  H8-8 (不含/含减值): {'✓ PASS' if h8_8_ok else '✗ FAIL'} "
          f"(found {branch_validation['h8_8_branches']['count']} branches)")
    if branch_validation["h8_8_branches"]["sheet_names"]:
        for sn in branch_validation["h8_8_branches"]["sheet_names"]:
            print(f"    - {sn}")

    # 总体验证摘要
    summary["validation"] = {
        "sheet_count_ok": len(sheet_names) == 20,
        "actual_sheet_count": len(sheet_names),
        "expected_sheet_count": 20,
        "h8_6_dual_branch_ok": h8_6_ok,
        "h8_8_dual_branch_ok": h8_8_ok,
        "all_branches_verified": h8_6_ok and h8_8_ok,
        "all_sheets_have_data": all(
            s["max_row"] > 0 for s in summary["sheets"]
        ),
        "total_formula_cells": sum(
            s["formula_count"] for s in summary["sheets"]
        ),
        "total_merged_ranges": sum(
            len(s["merged_ranges"]) for s in summary["sheets"]
        ),
    }

    # 写出JSON
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\nOutput written to: {OUTPUT_PATH}")
    print(f"\n=== Validation Summary ===")
    print(f"  Sheet count: {len(sheet_names)}/20 "
          f"({'OK' if summary['validation']['sheet_count_ok'] else 'MISMATCH'})")
    print(f"  H8-6 dual branches: {'OK' if h8_6_ok else 'MISSING'}")
    print(f"  H8-8 dual branches: {'OK' if h8_8_ok else 'MISSING'}")
    print(f"  All branches verified: {'✓ PASS' if summary['validation']['all_branches_verified'] else '✗ FAIL'}")
    print(f"  Total formulas: {summary['validation']['total_formula_cells']}")
    print(f"  Total merged ranges: {summary['validation']['total_merged_ranges']}")

    # 逐sheet摘要
    print("\n--- Per-Sheet Summary ---")
    print(f"{'#':<3s} {'Sheet':<45s} {'Rows':>5s} {'Cols':>5s} {'Formulas':>8s} {'Merges':>7s}")
    print("-" * 80)
    for idx, s in enumerate(summary["sheets"]):
        print(
            f"{idx+1:<3d} {s['sheet_name']:<45s} {s['max_row']:>5d} {s['max_column']:>5d} "
            f"{s['formula_count']:>8d} {len(s['merged_ranges']):>7d}"
        )

    wb.close()


if __name__ == "__main__":
    main()
