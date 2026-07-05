"""
dump_l1_structure.py
====================
读取 L1 短期借款.xlsx 全部 13 个 sheet，提取结构信息并输出 JSON。

产出：backend/scripts/output/l1_structure_summary.json

用法：python backend/scripts/dump_l1_structure.py
"""

import json
import os
import sys
from pathlib import Path

import openpyxl


# ---------- 配置 ----------

# 源文件：优先用 wp_templates 副本（较短路径），若不存在回退到原始目录
_CANDIDATES = [
    Path(r"backend/wp_templates/L/L1 短期借款.xlsx"),
    Path(
        r"数据/致同通用审计程序及底稿模板（2025年修订）"
        r"/1.致同审计程序及底稿模板（2025年）"
        r"/4.风险应对-实质性程序（D-N）/L 债务循环/L1 短期借款.xlsx"
    ),
]

OUTPUT_DIR = Path("backend/scripts/output")
OUTPUT_FILE = OUTPUT_DIR / "l1_structure_summary.json"


def find_source_file() -> Path:
    """按候选列表查找第一个存在的 xlsx 文件。"""
    for candidate in _CANDIDATES:
        if candidate.exists():
            return candidate
    # 尝试绝对路径
    for candidate in _CANDIDATES:
        abs_path = Path(os.getcwd()) / candidate
        if abs_path.exists():
            return abs_path
    print("ERROR: 找不到 L1 短期借款.xlsx，尝试过：")
    for c in _CANDIDATES:
        print(f"  - {c}")
    sys.exit(1)


def extract_headers(ws, max_row: int = 3) -> list[str]:
    """从前几行提取列头（取第一个非空行的值）。"""
    for row_idx in range(1, min(max_row + 1, ws.max_row + 1)):
        headers = []
        for col_idx in range(1, ws.max_column + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            val = cell.value
            if val is not None:
                headers.append(str(val).strip())
            else:
                headers.append("")
        # 如果这行有超过一半的单元格有值，就认为是列头行
        non_empty = sum(1 for h in headers if h)
        if non_empty >= max(2, len(headers) * 0.3):
            return [h for h in headers if h]  # 只返回非空
    return []


def extract_formulas(ws) -> dict:
    """提取公式单元格信息。"""
    formulas = []
    formula_count = 0
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=ws.max_column):
        for cell in row:
            if cell.value and isinstance(cell.value, str) and cell.value.startswith("="):
                formula_count += 1
                if len(formulas) < 10:  # 只保留前 10 个样例
                    formulas.append(
                        f"{cell.coordinate}: {cell.value}"
                    )
    return {"count": formula_count, "samples": formulas}


def extract_interest_calc_structure(ws) -> dict:
    """专门提取利息测算表 L1-5 的详细结构。"""
    structure = {
        "sheet_name": ws.title,
        "dimensions": f"{ws.max_row}行 × {ws.max_column}列",
        "headers_row1": [],
        "headers_row2": [],
        "headers_row3": [],
        "merged_cells": [],
        "formula_cells": [],
        "data_regions": [],
    }

    # 前 3 行列头
    for row_idx in range(1, min(4, ws.max_row + 1)):
        row_headers = []
        for col_idx in range(1, ws.max_column + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            val = cell.value
            row_headers.append(str(val).strip() if val else "")
        structure[f"headers_row{row_idx}"] = [h for h in row_headers if h]

    # 合并单元格
    for merged_range in ws.merged_cells.ranges:
        structure["merged_cells"].append(str(merged_range))

    # 公式单元格（全部记录）
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=ws.max_column):
        for cell in row:
            if cell.value and isinstance(cell.value, str) and cell.value.startswith("="):
                structure["formula_cells"].append(
                    {"cell": cell.coordinate, "formula": cell.value}
                )

    return structure


def main():
    # 切换到项目根目录
    project_root = Path(__file__).resolve().parent.parent.parent
    os.chdir(project_root)

    source_file = find_source_file()
    print(f"读取文件: {source_file}")

    # data_only=False 以读取公式而非计算结果
    wb = openpyxl.load_workbook(str(source_file), data_only=False, read_only=False)

    result = {
        "file_path": str(source_file),
        "sheet_count": len(wb.sheetnames),
        "sheet_names": wb.sheetnames,
        "sheets": [],
        "interest_calc_l1_5": None,
    }

    print(f"共 {len(wb.sheetnames)} 个 sheet:")
    for idx, name in enumerate(wb.sheetnames, 1):
        ws = wb[name]
        print(f"  [{idx:2d}] {name} ({ws.max_row}行 × {ws.max_column}列)")

        formula_info = extract_formulas(ws)
        headers = extract_headers(ws)

        sheet_info = {
            "name": name,
            "rows": ws.max_row,
            "cols": ws.max_column,
            "headers": headers,
            "formula_count": formula_info["count"],
            "formulas_sample": formula_info["samples"],
            "merged_cell_count": len(list(ws.merged_cells.ranges)),
        }
        result["sheets"].append(sheet_info)

        # 识别利息测算表 L1-5
        if "L1-5" in name or "利息测算" in name:
            result["interest_calc_l1_5"] = extract_interest_calc_structure(ws)

    # 输出
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 产出文件: {OUTPUT_FILE}")
    print(f"   sheet 数量: {result['sheet_count']}")
    total_formulas = sum(s["formula_count"] for s in result["sheets"])
    print(f"   公式总数: {total_formulas}")
    if result["interest_calc_l1_5"]:
        l15 = result["interest_calc_l1_5"]
        print(f"   利息测算表 L1-5: {l15['dimensions']}, {len(l15['formula_cells'])} 个公式")
    else:
        print("   ⚠️ 未找到利息测算表 L1-5")

    wb.close()


if __name__ == "__main__":
    main()
