"""
N4 税金及附加 xlsx 源模板结构摘要提取脚本
Phase 0, Task 0.1: 使用 openpyxl 读取 N4 xlsx，提取结构化摘要。

产出: tools/n4_structure_summary.json
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


# 源模板路径（优先级：wp_templates > 基础数据原始模板）
TEMPLATE_PATHS = [
    Path(r"d:\GT_plan\backend\wp_templates\N\N4 税金及附加.xlsx"),
    Path(r"d:\GT_plan\基础数据\致同通用审计程序及底稿模板（2025年修订）\1.致同审计程序及底稿模板（2025年）\4.风险应对-实质性程序（D-N）\N 税金循环\N4 税金及附加.xlsx"),
]

OUTPUT_PATH = Path(r"d:\GT_plan\tools\n4_structure_summary.json")


def find_template() -> Path | None:
    """查找可用的 xlsx 模板文件"""
    for p in TEMPLATE_PATHS:
        if p.exists():
            return p
    return None


def extract_headers(ws, max_col: int) -> dict:
    """提取第1行和第2行列头"""
    headers = {}
    for row_idx in (1, 2):
        row_data = []
        for col_idx in range(1, max_col + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            val = cell.value
            if val is not None:
                row_data.append({"col": get_column_letter(col_idx), "value": str(val).strip()})
        if row_data:
            headers[f"row_{row_idx}"] = row_data
    return headers


def count_formulas(ws, max_row: int, max_col: int) -> list[dict]:
    """统计公式单元格数量并收集公式样本"""
    formula_count = 0
    formula_samples = []
    for row in range(1, max_row + 1):
        for col in range(1, max_col + 1):
            cell = ws.cell(row=row, column=col)
            if cell.data_type == "f" or (isinstance(cell.value, str) and cell.value.startswith("=")):
                formula_count += 1
                if len(formula_samples) < 5:
                    formula_samples.append({
                        "cell": f"{get_column_letter(col)}{row}",
                        "formula": str(cell.value)
                    })
    return formula_count, formula_samples


def extract_sheet_info(ws) -> dict:
    """提取单个 sheet 的结构信息"""
    max_row = ws.max_row or 0
    max_col = ws.max_column or 0

    # 列头
    headers = extract_headers(ws, max_col)

    # 公式统计
    formula_count, formula_samples = count_formulas(ws, max_row, max_col)

    # 合并区域
    merged_count = len(ws.merged_cells.ranges)
    merged_samples = [str(m) for m in list(ws.merged_cells.ranges)[:5]]

    # 数据类型分布
    data_types = {}
    for row in ws.iter_rows(min_row=1, max_row=min(max_row, 50), max_col=max_col):
        for cell in row:
            dt = cell.data_type
            data_types[dt] = data_types.get(dt, 0) + 1

    return {
        "sheet_name": ws.title,
        "dimensions": f"{max_row}×{max_col}",
        "max_row": max_row,
        "max_col": max_col,
        "headers": headers,
        "formula_count": formula_count,
        "formula_samples": formula_samples,
        "merged_regions_count": merged_count,
        "merged_samples": merged_samples,
        "data_type_distribution": data_types,
    }


def generate_fallback_summary() -> dict:
    """找不到 xlsx 时，基于 spec tasks.md 描述生成结构摘要"""
    return {
        "source": "spec description (N4 tasks.md Phase 0)",
        "template_not_found": True,
        "searched_paths": [str(p) for p in TEMPLATE_PATHS],
        "sheets": [
            {"name": "底稿目录", "rows": None, "cols": None},
            {"name": "N4A 审计程序表", "rows": None, "cols": None, "note": "skip: use a-program-console"},
            {"name": "N4-1 审定表", "rows": 24, "cols": 14, "formulas": 83},
            {"name": "N4-2 明细表", "rows": 34, "cols": 11, "formulas": 18},
            {"name": "N4-3 调整分录", "rows": None, "cols": None},
            {"name": "附注披露(上市)", "rows": 18, "cols": 12},
            {"name": "附注披露(国企)", "rows": 17, "cols": 11},
            {"name": "O2A", "rows": None, "cols": None, "note": "skip: 原底稿"},
        ],
        "key_facts": {
            "account_code": "6403",
            "account_type": "损益类",
            "direction": "借方（费用）",
            "取数逻辑": "本期发生额 = 借方发生 - 贷方发生（从tb_ledger）",
            "公式总数": "~110+",
            "与N2关系": "N4费用确认 = N2计提额",
        },
    }


def main():
    template_path = find_template()

    if template_path is None:
        print("WARNING: N4 xlsx 模板文件未找到，使用 spec 描述生成 fallback 摘要")
        summary = generate_fallback_summary()
    else:
        print(f"读取模板: {template_path}")
        wb = load_workbook(str(template_path), data_only=False, read_only=False)

        sheets = []
        total_formulas = 0
        skip_sheets = []

        for ws in wb.worksheets:
            info = extract_sheet_info(ws)
            total_formulas += info["formula_count"]

            # 标记 skip sheet
            sheet_name = ws.title
            if "O2A" in sheet_name or "原底稿" in sheet_name:
                info["skip"] = True
                info["skip_reason"] = "O2A原底稿"
                skip_sheets.append(sheet_name)
            elif "N4A" in sheet_name or "审计程序" in sheet_name:
                info["skip"] = True
                info["skip_reason"] = "use a-program-console"
                skip_sheets.append(sheet_name)

            sheets.append(info)

        wb.close()

        summary = {
            "source": str(template_path),
            "source_type": "openpyxl extraction",
            "total_sheets": len(sheets),
            "total_formulas": total_formulas,
            "skip_sheets": skip_sheets,
            "sheets": sheets,
            "key_facts": {
                "account_code": "6403",
                "account_type": "损益类",
                "direction": "借方（费用）",
                "取数逻辑": "本期发生额 = 借方发生 - 贷方发生（从tb_ledger）",
                "公式总数": f"~{total_formulas}",
                "与N2关系": "N4费用确认 = N2计提额",
            },
        }

    # 写入 JSON
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 结构摘要已写入: {OUTPUT_PATH}")
    print(f"   sheets: {len(summary['sheets'])}")
    if "total_formulas" in summary:
        print(f"   公式总数: {summary['total_formulas']}")
    print(f"   skip: {summary.get('skip_sheets', [])}")


if __name__ == "__main__":
    main()
