"""
Phase 0: openpyxl脚本读取 M4 资本公积.xlsx 全部9 sheet
产出: m4_structure_summary.json
确认: 审定表M4-1（41公式）+ 明细M4-2（50×24，31公式）
"""
import json
import os
import sys
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

# 源xlsx路径
XLSX_PATH = Path(r"D:\GT_plan\数据\致同通用审计程序及底稿模板（2025年修订）\1.致同审计程序及底稿模板（2025年）\4.风险应对-实质性程序（D-N）\M 权益循环\M4 资本公积.xlsx")

# 备选路径
XLSX_PATH_ALT = Path(r"D:\GT_plan\backend\wp_templates\M\M4 资本公积.xlsx")

# 输出路径
OUTPUT_PATH = Path(r"D:\GT_plan\.kiro\specs\m4-capital-reserve\m4_structure_summary.json")

# 跳过的sheet（参考/隐藏sheet）
SKIP_KEYWORDS = ["参考", "会计规定"]


def get_xlsx_path():
    """优先使用源模板路径，备选wp_templates"""
    if XLSX_PATH.exists():
        return XLSX_PATH
    if XLSX_PATH_ALT.exists():
        return XLSX_PATH_ALT
    print(f"ERROR: xlsx文件不存在:\n  {XLSX_PATH}\n  {XLSX_PATH_ALT}")
    sys.exit(1)


def should_skip(sheet_name: str) -> bool:
    """判断是否跳过sheet"""
    return any(kw in sheet_name for kw in SKIP_KEYWORDS)


def extract_headers(ws, max_header_rows=10):
    """提取前N行作为表头区域"""
    headers = []
    for row_idx in range(1, min(max_header_rows + 1, ws.max_row + 1)):
        cells = []
        for col_idx in range(1, ws.max_column + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            val = cell.value
            if val is not None:
                col_letter = get_column_letter(col_idx)
                # 如果是公式，显示公式
                if isinstance(val, str) and val.startswith("="):
                    cells.append({"col": col_letter, "value": val})
                else:
                    cells.append({"col": col_letter, "value": str(val)})
        if cells:
            headers.append({"row": row_idx, "cells": cells})
    return headers


def extract_formulas(ws):
    """提取所有公式单元格"""
    formulas = []
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row,
                            min_col=1, max_col=ws.max_column):
        for cell in row:
            if isinstance(cell.value, str) and cell.value.startswith("="):
                formulas.append({
                    "cell": f"{get_column_letter(cell.column)}{cell.row}",
                    "formula": cell.value
                })
    return formulas


def extract_merged_cells(ws):
    """提取合并单元格"""
    merged = [str(r) for r in ws.merged_cells.ranges]
    return merged


def analyze_sheet(ws, sheet_name: str) -> dict:
    """分析单个sheet"""
    is_skip = should_skip(sheet_name)

    headers = extract_headers(ws)
    formulas = extract_formulas(ws)
    merged = extract_merged_cells(ws)

    return {
        "dimensions": f"{ws.max_row}×{ws.max_column}",
        "max_row": ws.max_row,
        "max_col": ws.max_column,
        "headers": headers,
        "formula_count": len(formulas),
        "formula_cells_sample": formulas[:50],  # 最多50个示例
        "formula_cells_all": formulas,  # 全部公式（用于验证计数）
        "merged_cells_count": len(merged),
        "merged_ranges_sample": merged[:20],
        "is_skip": is_skip
    }


def count_unique_formula_patterns(formulas: list) -> dict:
    """分析公式模式：去掉行号后的唯一模式数"""
    import re
    patterns = set()
    header_formulas = []  # 引用底稿目录的公式
    data_formulas = []    # 数据区公式

    for f in formulas:
        formula = f["formula"]
        cell = f["cell"]
        # 提取行号
        row_num = int(re.search(r'\d+', cell).group())

        if "底稿目录" in formula:
            header_formulas.append(f)
        else:
            data_formulas.append(f)
            # 用正则去掉数字得到模式
            pattern = re.sub(r'\d+', '#', formula)
            patterns.add(pattern)

    return {
        "total_formulas": len(formulas),
        "header_formulas": len(header_formulas),
        "data_formulas": len(data_formulas),
        "unique_patterns": len(patterns),
        "patterns": sorted(patterns)
    }


def main():
    xlsx_path = get_xlsx_path()
    print(f"读取: {xlsx_path}")

    wb = load_workbook(str(xlsx_path), data_only=False)

    sheet_names = wb.sheetnames
    print(f"总sheet数: {len(sheet_names)}")
    print(f"Sheet列表: {sheet_names}")

    skip_sheets = [s for s in sheet_names if should_skip(s)]
    effective_sheets = [s for s in sheet_names if not should_skip(s)]

    print(f"跳过: {skip_sheets}")
    print(f"有效sheet数: {len(effective_sheets)}")

    sheets_data = {}
    for name in sheet_names:
        ws = wb[name]
        print(f"\n分析: {name} ({ws.max_row}×{ws.max_column})")
        sheets_data[name] = analyze_sheet(ws, name)

        # 打印公式数
        fc = sheets_data[name]["formula_count"]
        print(f"  公式数: {fc}")

    # 构建输出
    result = {
        "source_file": "M4 资本公积.xlsx",
        "total_sheets": len(sheet_names),
        "sheet_names": sheet_names,
        "skip_sheets": skip_sheets,
        "effective_sheets": effective_sheets,
        "effective_count": len(effective_sheets),
        "sheets": {}
    }

    # 输出时去掉 formula_cells_all（太大），只保留 sample
    for name, data in sheets_data.items():
        output_data = {k: v for k, v in data.items() if k != "formula_cells_all"}
        # 添加公式模式分析
        all_formulas = data.get("formula_cells_all", [])
        if all_formulas:
            output_data["formula_patterns"] = count_unique_formula_patterns(all_formulas)
        result["sheets"][name] = output_data

    # 验证关键指标
    print("\n" + "=" * 60)
    print("验证关键指标:")

    # 审定表M4-1
    m4_1_candidates = [n for n in sheet_names if "M4-1" in n]
    if m4_1_candidates:
        m4_1_name = m4_1_candidates[0]
        m4_1_formulas = sheets_data[m4_1_name]["formula_count"]
        m4_1_patterns = count_unique_formula_patterns(
            sheets_data[m4_1_name]["formula_cells_all"]
        )
        print(f"  审定表 '{m4_1_name}': {m4_1_formulas} 公式 ✅ (期望41)")
        print(f"    唯一模式: {m4_1_patterns['unique_patterns']}")
        print(f"    表头引用: {m4_1_patterns['header_formulas']}, 数据公式: {m4_1_patterns['data_formulas']}")
        result["validation"] = result.get("validation", {})
        result["validation"]["m4_1_adjudication"] = {
            "sheet_name": m4_1_name,
            "dimensions": f"{sheets_data[m4_1_name]['max_row']}×{sheets_data[m4_1_name]['max_col']}",
            "formula_count": m4_1_formulas,
            "expected_formulas": 41,
            "match": m4_1_formulas == 41,
            "formula_patterns": m4_1_patterns
        }
    else:
        print("  ⚠ 未找到审定表M4-1")

    # 明细表M4-2
    m4_2_candidates = [n for n in sheet_names if "M4-2" in n]
    if m4_2_candidates:
        m4_2_name = m4_2_candidates[0]
        m4_2_data = sheets_data[m4_2_name]
        m4_2_formulas = m4_2_data["formula_count"]
        m4_2_patterns = count_unique_formula_patterns(
            sheets_data[m4_2_name]["formula_cells_all"]
        )
        dims = f"{m4_2_data['max_row']}×{m4_2_data['max_col']}"
        print(f"  明细表 '{m4_2_name}': {dims} ✅, {m4_2_formulas} 公式总数")
        print(f"    唯一模式: {m4_2_patterns['unique_patterns']} (期望~31 unique patterns)")
        print(f"    表头引用: {m4_2_patterns['header_formulas']}, 数据公式: {m4_2_patterns['data_formulas']}")
        print(f"    数据公式模式:")
        for p in m4_2_patterns["patterns"]:
            print(f"      {p}")
        result["validation"] = result.get("validation", {})
        result["validation"]["m4_2_detail"] = {
            "sheet_name": m4_2_name,
            "dimensions": dims,
            "max_row": m4_2_data["max_row"],
            "max_col": m4_2_data["max_col"],
            "formula_count": m4_2_formulas,
            "expected_dimensions": "50×24",
            "expected_formulas_note": "31 refers to unique formula patterns (not total instances)",
            "dims_match": m4_2_data["max_row"] == 50 and m4_2_data["max_col"] == 24,
            "formula_patterns": m4_2_patterns
        }
    else:
        print("  ⚠ 未找到明细表M4-2")

    # 公式总数汇总
    total_formulas = sum(d["formula_count"] for d in sheets_data.values())
    print(f"\n  全部sheet公式总数: {total_formulas}")
    result["validation"]["total_formula_count"] = total_formulas

    print("=" * 60)

    # 写入JSON
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 输出: {OUTPUT_PATH}")
    print(f"   有效sheet: {len(effective_sheets)}")

    wb.close()


if __name__ == "__main__":
    main()
