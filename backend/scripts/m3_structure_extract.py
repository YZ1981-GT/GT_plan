"""
M3 库存股.xlsx 结构提取脚本
Phase 0 Task 0.1: 读取全部sheet，提取结构+确认审定表M3-1（73公式）+明细M3-2（59×19）+外币M3-4
识别会计规定辅助sheet跳过

产出: .kiro/specs/m3-treasury-stock/m3_structure_summary.json
"""
import json
import os
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

# 源文件路径（致同2025修订版源模板）
XLSX_PATH = (
    r"D:\GT_plan\数据\致同通用审计程序及底稿模板（2025年修订）"
    r"\1.致同审计程序及底稿模板（2025年）"
    r"\4.风险应对-实质性程序（D-N）\M 权益循环"
    r"\M3 库存股.xlsx"
)

OUTPUT_PATH = (
    Path(__file__).parent.parent.parent
    / ".kiro"
    / "specs"
    / "m3-treasury-stock"
    / "m3_structure_summary.json"
)


def extract_sheet_structure(ws):
    """提取单个sheet的结构信息"""
    max_row = ws.max_row or 0
    max_col = ws.max_column or 0

    # 提取前8行的列头（M3可能有多行表头）
    headers = []
    for row_idx in range(1, min(9, max_row + 1)):
        row_data = []
        for col_idx in range(1, max_col + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            val = cell.value
            if val is not None:
                row_data.append({
                    "col": get_column_letter(col_idx),
                    "value": str(val)[:100]
                })
        if row_data:
            headers.append({"row": row_idx, "cells": row_data})

    # 统计公式单元格
    formula_cells = []
    formula_count = 0
    for row in ws.iter_rows(min_row=1, max_row=max_row, max_col=max_col):
        for cell in row:
            if cell.value and isinstance(cell.value, str) and cell.value.startswith("="):
                formula_count += 1
                if len(formula_cells) < 80:
                    formula_cells.append({
                        "cell": f"{get_column_letter(cell.column)}{cell.row}",
                        "formula": str(cell.value)[:200]
                    })

    # 统计合并单元格
    merged_ranges = [str(r) for r in ws.merged_cells.ranges]

    return {
        "dimensions": f"{max_row}×{max_col}",
        "max_row": max_row,
        "max_col": max_col,
        "headers": headers,
        "formula_count": formula_count,
        "formula_cells_sample": formula_cells,
        "merged_cells_count": len(merged_ranges),
        "merged_ranges_sample": merged_ranges[:30],
    }


def identify_skip_sheets(sheet_names):
    """识别应跳过的辅助sheet（会计规定辅助等）"""
    skip_keywords = ["会计规定", "辅助", "规定辅助"]
    skip_sheets = []
    for name in sheet_names:
        for kw in skip_keywords:
            if kw in name:
                skip_sheets.append(name)
                break
    return skip_sheets


def main():
    print(f"读取文件: {XLSX_PATH}")
    assert os.path.exists(XLSX_PATH), f"文件不存在: {XLSX_PATH}"

    # data_only=False 以保留公式
    wb = load_workbook(XLSX_PATH, data_only=False, read_only=False)

    sheet_names = wb.sheetnames
    print(f"共 {len(sheet_names)} 个sheet: {sheet_names}")

    # 识别跳过的辅助sheet
    skip_sheets = identify_skip_sheets(sheet_names)
    effective_sheets = [n for n in sheet_names if n not in skip_sheets]

    result = {
        "source_file": "M3 库存股.xlsx",
        "total_sheets": len(sheet_names),
        "sheet_names": sheet_names,
        "skip_sheets": skip_sheets,
        "effective_sheets": effective_sheets,
        "effective_count": len(effective_sheets),
        "sheets": {},
        "key_sheet_validation": {},
    }

    total_formulas = 0
    for name in sheet_names:
        ws = wb[name]
        is_skip = name in skip_sheets
        print(f"  处理: {name} {'[SKIP-会计规定辅助]' if is_skip else ''} ...")
        structure = extract_sheet_structure(ws)
        structure["is_skip"] = is_skip
        result["sheets"][name] = structure
        total_formulas += structure["formula_count"]
        print(f"    维度: {structure['dimensions']}, 公式: {structure['formula_count']}")

    result["total_formulas"] = total_formulas

    # === 关键sheet验证 ===

    # 1. M3-1 审定表 (spec估计33×12, 73公式)
    m3_1_candidates = [n for n in sheet_names if "M3-1" in n or "审定" in n]
    if m3_1_candidates:
        m3_1_name = m3_1_candidates[0]
        m3_1_info = result["sheets"][m3_1_name]
        result["key_sheet_validation"]["M3-1_审定表"] = {
            "sheet_name": m3_1_name,
            "spec_estimate_dimensions": "33×12",
            "actual_dimensions": m3_1_info["dimensions"],
            "spec_estimate_formulas": 73,
            "actual_formulas": m3_1_info["formula_count"],
            "note": "权益备抵借方科目（期末=期初+借方-贷方）",
        }

    # 2. M3-2 明细表 (spec估计59×19)
    m3_2_candidates = [n for n in sheet_names if "M3-2" in n or "明细" in n]
    if m3_2_candidates:
        m3_2_name = m3_2_candidates[0]
        m3_2_info = result["sheets"][m3_2_name]
        result["key_sheet_validation"]["M3-2_明细表"] = {
            "sheet_name": m3_2_name,
            "spec_estimate_dimensions": "59×19",
            "actual_dimensions": m3_2_info["dimensions"],
            "spec_estimate_formulas": m3_2_info["formula_count"],
            "note": "按回购批次列示库存股明细",
        }

    # 3. M3-4 外币投资汇率
    m3_4_candidates = [n for n in sheet_names if "M3-4" in n or "外币" in n]
    if m3_4_candidates:
        m3_4_name = m3_4_candidates[0]
        m3_4_info = result["sheets"][m3_4_name]
        result["key_sheet_validation"]["M3-4_外币投资汇率"] = {
            "sheet_name": m3_4_name,
            "actual_dimensions": m3_4_info["dimensions"],
            "actual_formulas": m3_4_info["formula_count"],
            "note": "外币回购折算",
        }

    # 4. 会计规定辅助sheet（确认跳过）
    if skip_sheets:
        for skip_name in skip_sheets:
            skip_info = result["sheets"][skip_name]
            result["key_sheet_validation"][f"SKIP_{skip_name}"] = {
                "sheet_name": skip_name,
                "dimensions": skip_info["dimensions"],
                "action": "跳过（会计规定辅助，不渲染为专属组件）",
            }

    # 5. 其他有效sheet检测：M3-3调整/M3-5检查表/目录/附注/M3A
    other_keywords = {
        "M3-3": "调整分录",
        "M3-5": "检查表（回购/注销核对）",
        "目录": "底稿目录",
        "附注": "附注披露",
        "M3A": "实质性程序表",
    }
    for kw, desc in other_keywords.items():
        candidates = [n for n in sheet_names if kw in n]
        for name in candidates:
            info = result["sheets"][name]
            result["key_sheet_validation"][f"{kw}_{desc}"] = {
                "sheet_name": name,
                "dimensions": info["dimensions"],
                "formula_count": info["formula_count"],
                "description": desc,
            }

    # 输出JSON
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n产出文件: {OUTPUT_PATH}")
    print(f"总公式数: {total_formulas}")
    print(f"有效sheet数: {len(effective_sheets)} / 总计: {len(sheet_names)}")
    print(f"跳过sheet: {skip_sheets}")

    print("\n=== 关键sheet验证 ===")
    for key, val in result["key_sheet_validation"].items():
        print(f"  📋 {key}:")
        for k, v in val.items():
            print(f"      {k}: {v}")

    wb.close()


if __name__ == "__main__":
    main()
