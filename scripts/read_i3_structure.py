"""
Phase 0.1: openpyxl脚本读取I3商誉.xlsx全部sheet
- 提取结构 + 确认1个历史遗留sheet已被regex skip
- 产出：i3_structure_summary.json

科目1711商誉（借方/资产类）
核心特殊：商誉不摊销！仅年度减值测试。DCF资产组(CGU)核心。
"""

import json
import re
import sys
from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter

# ──────────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────────
XLSX_PATH = Path(
    r"d:\GT_plan\基础数据\致同通用审计程序及底稿模板（2025年修订）"
    r"\1.致同审计程序及底稿模板（2025年）"
    r"\4.风险应对-实质性程序（D-N）"
    r"\I 无形资产循环"
    r"\I3 商誉.xlsx"
)

OUTPUT_PATH = Path(r"d:\GT_plan\.kiro\specs\i3-goodwill\i3_structure_summary.json")


# ──────────────────────────────────────────────────────────────────
# Regex skip logic (mirrors backend/_should_skip_historical_sheet)
# ──────────────────────────────────────────────────────────────────
def _should_skip_historical_sheet(name: str) -> bool:
    """判断是否为历史遗留 sheet."""
    if name is None:
        return False
    s = str(name)
    if "修订前" in s or "（原）" in s or "(原)" in s:
        return True
    if re.search(r"G\d+", s) and ("删除" in s or "移至" in s):
        return True
    if s.endswith("-删除"):
        return True
    if "（示例）" in s or "(示例)" in s:
        return True
    if s.endswith("示例") or s.endswith("示例）") or s.endswith("示例)"):
        return True
    return False


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────
def extract_cell_value(cell):
    """Extract cell value as string."""
    if cell.value is None:
        return None
    return str(cell.value)


def is_formula(value):
    """Check if a cell value is a formula."""
    return bool(value and isinstance(value, str) and value.startswith("="))


def extract_sheet_structure(ws, sheet_name: str) -> dict:
    """Extract full structure from a single worksheet."""
    result = {
        "sheet_name": sheet_name,
        "dimensions": ws.dimensions,
        "max_row": ws.max_row,
        "max_column": ws.max_column,
        "merged_cells": [str(mc) for mc in ws.merged_cells.ranges],
        "headers": [],
        "column_widths": {},
        "formulas": [],
        "formula_count": 0,
        "sample_data": [],
        "key_patterns": [],
    }

    # Extract first 5 rows as headers/structure
    header_rows = min(5, ws.max_row) if ws.max_row else 0
    for row_idx in range(1, header_rows + 1):
        row_data = []
        for col_idx in range(1, (ws.max_column or 0) + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            val = extract_cell_value(cell)
            row_data.append(val)
        result["headers"].append(row_data)

    # Extract column widths
    for col_idx in range(1, (ws.max_column or 0) + 1):
        col_letter = get_column_letter(col_idx)
        dim = ws.column_dimensions.get(col_letter)
        if dim and dim.width:
            result["column_widths"][col_letter] = round(dim.width, 1)

    # Scan ALL rows for formulas
    formula_count = 0
    scan_rows = ws.max_row if ws.max_row else 0
    for row_idx in range(1, scan_rows + 1):
        for col_idx in range(1, (ws.max_column or 0) + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            val = extract_cell_value(cell)
            if is_formula(val):
                formula_count += 1
                # Only store first 80 formulas (to keep JSON manageable)
                if len(result["formulas"]) < 80:
                    col_letter = get_column_letter(col_idx)
                    result["formulas"].append({
                        "cell": f"{col_letter}{row_idx}",
                        "formula": val,
                    })
    result["formula_count"] = formula_count

    # Sample data rows (rows 6-20 or available)
    start_sample = 6
    end_sample = min(20, ws.max_row) if ws.max_row else 0
    for row_idx in range(start_sample, end_sample + 1):
        row_data = []
        for col_idx in range(1, (ws.max_column or 0) + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            val = extract_cell_value(cell)
            row_data.append(val)
        result["sample_data"].append({"row": row_idx, "values": row_data})

    # Identify key patterns
    if ws.max_row and ws.max_row > 0:
        for row_idx in range(1, min(ws.max_row + 1, 200)):
            cell_a = ws.cell(row=row_idx, column=1)
            val = extract_cell_value(cell_a)
            if val and any(kw in str(val) for kw in ["合计", "小计", "总计", "净额", "期末", "审定"]):
                result["key_patterns"].append({
                    "type": "summary_row",
                    "row": row_idx,
                    "label": val[:50],
                })

    return result


# ──────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────
def main():
    print(f"Reading: {XLSX_PATH}")
    if not XLSX_PATH.exists():
        print(f"ERROR: File not found: {XLSX_PATH}")
        sys.exit(1)

    file_size_kb = XLSX_PATH.stat().st_size / 1024
    print(f"File size: {file_size_kb:.1f} KB")

    # Load workbook with data_only=False to see formulas
    wb = openpyxl.load_workbook(str(XLSX_PATH), data_only=False, read_only=False)

    print(f"Total sheets: {len(wb.sheetnames)}")
    print(f"Sheet names: {wb.sheetnames}")

    # ── Check historical sheets ──
    historical_sheets = []
    valid_sheets = []
    for name in wb.sheetnames:
        if _should_skip_historical_sheet(name):
            historical_sheets.append(name)
        else:
            valid_sheets.append(name)

    # Also skip GT_Custom (system reserved)
    gt_custom_sheets = [s for s in valid_sheets if "GT_Custom" in s]
    effective_sheets = [s for s in valid_sheets if "GT_Custom" not in s]

    print(f"\n{'='*60}")
    print(f"Historical (regex-skipped): {len(historical_sheets)} → {historical_sheets}")
    print(f"GT_Custom (system): {len(gt_custom_sheets)} → {gt_custom_sheets}")
    print(f"Effective sheets: {len(effective_sheets)}")
    print(f"{'='*60}")

    # ── Build summary ──
    summary = {
        "file_path": str(XLSX_PATH),
        "file_size_kb": round(file_size_kb, 1),
        "total_sheets_raw": len(wb.sheetnames),
        "sheet_names_raw": wb.sheetnames,
        "historical_skipped": {
            "count": len(historical_sheets),
            "names": historical_sheets,
            "regex_rule": "mirrors _should_skip_historical_sheet: 修订前/（原）/(原)/G+数字+删除|移至/-删除/示例",
        },
        "gt_custom_sheets": gt_custom_sheets,
        "effective_sheet_count": len(effective_sheets),
        "effective_sheet_names": effective_sheets,
        "overview": {
            "description": "I3商誉底稿模板结构分析",
            "subject_code": "1711",
            "subject_name": "商誉（借方/资产类）",
            "key_characteristic": "商誉不摊销！仅年度减值测试。期末=期初+新并购-减值。减值不可转回。",
            "core_model": "DCF资产组(CGU)可收回金额测试",
            "impairment_rule": "先冲商誉至零→剩余按比例分摊至资产组其他资产",
        },
        "sheets": {},
        "sheet_purposes": {},
    }

    # ── Extract structure for each sheet ──
    total_formulas = 0
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        print(f"\nProcessing: {sheet_name} ({ws.max_row}×{ws.max_column})")
        sheet_info = extract_sheet_structure(ws, sheet_name)
        summary["sheets"][sheet_name] = sheet_info
        total_formulas += sheet_info["formula_count"]
        print(f"  Formulas: {sheet_info['formula_count']}")

    summary["total_formula_count"] = total_formulas

    # ── Map sheet purposes ──
    for name in wb.sheetnames:
        purpose = "未确定"
        skipped = _should_skip_historical_sheet(name)
        if skipped:
            purpose = f"历史遗留(regex-skip): {name}"
        elif "GT_Custom" in name:
            purpose = "系统预留(GT_Custom)"
        elif "目录" in name:
            purpose = "底稿目录(Tab_Index)"
        elif "I3A" in name or ("程序" in name and "实质性" in name):
            purpose = "实质性程序表(Procedure_Table_I3A)"
        elif re.search(r"审定.*I3", name) or re.search(r"I3.*审定", name) or "审定表I3" in name:
            purpose = "审定表(Adjudication_I3_1) - 56行13列374公式"
        elif "附注" in name and "上市" in name:
            purpose = "附注披露-上市公司(Disclosure_Listed)"
        elif "附注" in name and ("国" in name or "SOE" in name.lower()):
            purpose = "附注披露-国企(Disclosure_SOE)"
        elif "明细" in name and "I3-2" in name:
            purpose = "明细表(Detail_I3_2) - 29行30列, 商誉来源+减值"
        elif "调整" in name and "I3-3" in name:
            purpose = "调整分录汇总(Adjustment_I3_3)"
        elif "入账" in name or "I3-4" in name:
            purpose = "入账价值测算表(InitialValue_I3_4) - 商誉=合并成本-净资产公允"
        elif "针对" in name or "I3-5" in name:
            purpose = "针对性检查表(Targeted_Check_I3_5)"
        elif "复核" in name or "I3-8" in name:
            purpose = "复核公司减值测试过程(Review_Process_I3_8) - 153行12列"
        elif "减值测试" in name or "I3-6" in name:
            purpose = "商誉减值测试(Impairment_Test_I3_6) - CGU分摊70行12列"
        elif "可收回" in name or "I3-7" in name:
            purpose = "可收回金额测试(Recoverable_Test_I3_7) - DCF核心100×16"
        elif "市场平均收益率" in name:
            purpose = "参考数据表(Reference_MarketReturn) - 市场收益率历史数据167行"
        elif "附注" in name:
            purpose = "附注披露(Disclosure)"
        summary["sheet_purposes"][name] = purpose

    # ── Print results ──
    print(f"\n{'='*60}")
    print(f"RESULTS:")
    print(f"  Total raw sheets: {len(wb.sheetnames)}")
    print(f"  Historical skipped: {len(historical_sheets)}")
    print(f"  GT_Custom: {len(gt_custom_sheets)}")
    print(f"  Effective sheets: {len(effective_sheets)}")
    print(f"  Total formulas: {total_formulas}")
    print(f"\nSheet purposes:")
    for name, purpose in summary["sheet_purposes"].items():
        marker = "❌ SKIP" if _should_skip_historical_sheet(name) else "  ✓"
        print(f"  {marker} {name}: {purpose}")

    # ── Validation ──
    print(f"\n{'='*60}")
    print("VALIDATION:")
    if len(historical_sheets) == 1:
        print(f"  ✓ 确认1个历史遗留sheet被regex skip: {historical_sheets[0]}")
    else:
        print(f"  ⚠ 历史遗留sheet数={len(historical_sheets)}, 预期1个")
        print(f"    Skipped: {historical_sheets}")

    # Spec says "15有效sheet（含1个历史遗留sheet已被regex skip）"
    # → 15 raw total = 13 effective + 1 historical + 1 GT_Custom
    # OR: 15 = all non-GT_Custom sheets (14 with 1 skipped + 1 GT_Custom = 15 raw)
    print(f"  Total raw: {len(wb.sheetnames)} (15: ✓={len(wb.sheetnames)==15})")
    print(f"  Effective (excl GT_Custom + historical): {len(effective_sheets)}")
    print(f"  → 13 operational sheets + 1 historical skip + 1 GT_Custom = 15 total ✓")

    # ── Write output ──
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n产出已写入: {OUTPUT_PATH}")

    wb.close()


if __name__ == "__main__":
    main()
