"""
Phase 0.1: openpyxl脚本读取L5长期应付款.xlsx全部9 sheet
提取结构 + 确认L5-5摊销测算表+L5-3未确认明细结构
产出：l5_structure_summary.json
"""

import json
from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter

# 源文件路径（致同2025修订版源模板）
XLSX_PATH = Path(
    r"d:\GT_plan\数据\致同通用审计程序及底稿模板（2025年修订）"
    r"\1.致同审计程序及底稿模板（2025年）"
    r"\4.风险应对-实质性程序（D-N）\L 债务循环\L5 长期应付款.xlsx"
)
OUTPUT_PATH = Path(r"d:\GT_plan\.kiro\specs\l5-long-term-payables\l5_structure_summary.json")


def extract_sheet_structure(ws):
    """提取单个sheet的结构信息"""
    info = {
        "title": ws.title,
        "dimensions": ws.dimensions,
        "max_row": ws.max_row,
        "max_column": ws.max_column,
        "dims_display": f"{ws.max_row}×{ws.max_column}",
        "merged_cells": [str(m) for m in ws.merged_cells.ranges],
        "merged_cells_count": len(ws.merged_cells.ranges),
        "headers": [],
        "formulas": [],
        "formula_count": 0,
        "sample_data": [],
    }

    # 提取前5行作为header候选
    for row_idx in range(1, min(6, ws.max_row + 1)):
        row_data = []
        for col_idx in range(1, ws.max_column + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            val = cell.value
            if val is not None:
                row_data.append({
                    "col": get_column_letter(col_idx),
                    "col_idx": col_idx,
                    "value": str(val)[:100],
                    "is_formula": str(val).startswith("=") if isinstance(val, str) else False,
                })
        if row_data:
            info["headers"].append({"row": row_idx, "cells": row_data})

    # 扫描所有公式
    formula_samples = []
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=ws.max_column):
        for cell in row:
            if isinstance(cell.value, str) and cell.value.startswith("="):
                info["formula_count"] += 1
                if len(formula_samples) < 15:
                    formula_samples.append({
                        "cell": f"{get_column_letter(cell.column)}{cell.row}",
                        "formula": cell.value[:200],
                    })
    info["formulas"] = formula_samples

    # 提取第6~10行sample data (如有)
    for row_idx in range(6, min(11, ws.max_row + 1)):
        row_data = []
        for col_idx in range(1, min(ws.max_column + 1, 20)):
            cell = ws.cell(row=row_idx, column=col_idx)
            val = cell.value
            if val is not None:
                row_data.append({
                    "col": get_column_letter(col_idx),
                    "value": str(val)[:100],
                    "is_formula": str(val).startswith("=") if isinstance(val, str) else False,
                })
        if row_data:
            info["sample_data"].append({"row": row_idx, "cells": row_data})

    return info


def confirm_l5_5_amortization(wb):
    """确认L5-5未确认融资费用测算表结构（核心！实际利率法）"""
    confirmation = {
        "found": False,
        "sheet_name": None,
        "details": {},
    }

    for name in wb.sheetnames:
        if "L5-5" in name or ("摊销" in name and "L5" in name) or "测算" in name:
            ws = wb[name]
            confirmation["found"] = True
            confirmation["sheet_name"] = name
            confirmation["details"] = {
                "rows": ws.max_row,
                "cols": ws.max_column,
                "dims": f"{ws.max_row}×{ws.max_column}",
                "all_headers": [],
                "has_amortized_cost_col": False,
                "has_eir_col": False,
                "has_amortization_col": False,
                "has_repayment_col": False,
                "has_period_col": False,
                "has_end_cost_col": False,
                "has_present_value_col": False,
                "has_initial_amount_col": False,
                "has_difference_col": False,
                "formula_count": 0,
                "formula_samples": [],
                "column_structure": {},
            }

            # 检查前12行header（L5-5表头在第9-11行）
            for row_idx in range(1, min(13, ws.max_row + 1)):
                for col_idx in range(1, ws.max_column + 1):
                    val = ws.cell(row=row_idx, column=col_idx).value
                    if val:
                        val_str = str(val)
                        confirmation["details"]["all_headers"].append({
                            "row": row_idx,
                            "col": get_column_letter(col_idx),
                            "col_idx": col_idx,
                            "value": val_str[:80]
                        })
                        # 检查关键列
                        if "摊余" in val_str or "期初" in val_str:
                            confirmation["details"]["has_amortized_cost_col"] = True
                        if "实际利率" in val_str or "折现率" in val_str:
                            confirmation["details"]["has_eir_col"] = True
                        if "摊销" in val_str or "确认" in val_str or "融资费用" in val_str:
                            confirmation["details"]["has_amortization_col"] = True
                        if "偿还" in val_str or "支付" in val_str or "还款" in val_str or "付款" in val_str:
                            confirmation["details"]["has_repayment_col"] = True
                        if "期数" in val_str or "期间" in val_str or "年份" in val_str or "年" in val_str:
                            confirmation["details"]["has_period_col"] = True
                        if "期末" in val_str or "余额" in val_str:
                            confirmation["details"]["has_end_cost_col"] = True
                        if "现值" in val_str:
                            confirmation["details"]["has_present_value_col"] = True
                        if "初始" in val_str:
                            confirmation["details"]["has_initial_amount_col"] = True
                        if "差异" in val_str:
                            confirmation["details"]["has_difference_col"] = True

            # 提取列结构（第9-11行为表头区域）
            col_struct = {}
            for col_idx in range(1, ws.max_column + 1):
                col_key = get_column_letter(col_idx)
                headers_for_col = []
                for row_idx in range(9, min(12, ws.max_row + 1)):
                    val = ws.cell(row=row_idx, column=col_idx).value
                    if val:
                        headers_for_col.append(str(val)[:60])
                if headers_for_col:
                    col_struct[col_key] = " | ".join(headers_for_col)
            confirmation["details"]["column_structure"] = col_struct

            # 扫描公式
            for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=ws.max_column):
                for cell in row:
                    if isinstance(cell.value, str) and cell.value.startswith("="):
                        confirmation["details"]["formula_count"] += 1
                        if len(confirmation["details"]["formula_samples"]) < 10:
                            confirmation["details"]["formula_samples"].append({
                                "cell": f"{get_column_letter(cell.column)}{cell.row}",
                                "formula": cell.value[:200],
                            })
            break

    return confirmation


def confirm_l5_3_unrecognized_detail(wb):
    """确认L5-3未确认融资费用明细表结构"""
    confirmation = {
        "found": False,
        "sheet_name": None,
        "details": {},
    }

    for name in wb.sheetnames:
        if "L5-3" in name or ("未确认" in name and "L5" in name):
            ws = wb[name]
            confirmation["found"] = True
            confirmation["sheet_name"] = name
            confirmation["details"] = {
                "rows": ws.max_row,
                "cols": ws.max_column,
                "dims": f"{ws.max_row}×{ws.max_column}",
                "all_headers": [],
                "has_initial_unrecognized_col": False,
                "has_period_amortization_col": False,
                "has_cumulative_amortization_col": False,
                "has_balance_col": False,
                "has_loan_item_col": False,
                "has_begin_balance_col": False,
                "has_increase_col": False,
                "has_decrease_col": False,
                "formula_count": 0,
                "formula_samples": [],
                "column_structure": {},
            }

            # 检查前12行header（L5-3实际表头可能在第6-10行）
            for row_idx in range(1, min(13, ws.max_row + 1)):
                for col_idx in range(1, ws.max_column + 1):
                    val = ws.cell(row=row_idx, column=col_idx).value
                    if val:
                        val_str = str(val)
                        confirmation["details"]["all_headers"].append({
                            "row": row_idx,
                            "col": get_column_letter(col_idx),
                            "col_idx": col_idx,
                            "value": val_str[:80]
                        })
                        # 检查关键列
                        if "初始" in val_str or "原始" in val_str or "原值" in val_str:
                            confirmation["details"]["has_initial_unrecognized_col"] = True
                        if "本期" in val_str and ("摊销" in val_str or "确认" in val_str):
                            confirmation["details"]["has_period_amortization_col"] = True
                        if "累计" in val_str:
                            confirmation["details"]["has_cumulative_amortization_col"] = True
                        if "余额" in val_str or "期末" in val_str:
                            confirmation["details"]["has_balance_col"] = True
                        if "款项" in val_str or "名称" in val_str or "来源" in val_str or "项目" in val_str:
                            confirmation["details"]["has_loan_item_col"] = True
                        if "期初" in val_str:
                            confirmation["details"]["has_begin_balance_col"] = True
                        if "增加" in val_str or "新增" in val_str:
                            confirmation["details"]["has_increase_col"] = True
                        if "减少" in val_str or "摊销" in val_str or "转回" in val_str:
                            confirmation["details"]["has_decrease_col"] = True

            # 提取列结构（第6-10行为表头区域）
            col_struct = {}
            for col_idx in range(1, ws.max_column + 1):
                col_key = get_column_letter(col_idx)
                headers_for_col = []
                for row_idx in range(5, min(12, ws.max_row + 1)):
                    val = ws.cell(row=row_idx, column=col_idx).value
                    if val:
                        headers_for_col.append(str(val)[:60])
                if headers_for_col:
                    col_struct[col_key] = " | ".join(headers_for_col)
            confirmation["details"]["column_structure"] = col_struct

            # 扫描公式
            for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=ws.max_column):
                for cell in row:
                    if isinstance(cell.value, str) and cell.value.startswith("="):
                        confirmation["details"]["formula_count"] += 1
                        if len(confirmation["details"]["formula_samples"]) < 10:
                            confirmation["details"]["formula_samples"].append({
                                "cell": f"{get_column_letter(cell.column)}{cell.row}",
                                "formula": cell.value[:200],
                            })
            break

    return confirmation


def main():
    if not XLSX_PATH.exists():
        # 尝试备选路径
        alt_path = Path(r"d:\GT_plan\backend\wp_templates\L\L5 长期应付款.xlsx")
        if alt_path.exists():
            xlsx_path = alt_path
            print(f"使用备选路径: {alt_path}")
        else:
            print(f"ERROR: 源文件不存在: {XLSX_PATH}")
            print(f"  备选路径也不存在: {alt_path}")
            return
    else:
        xlsx_path = XLSX_PATH

    print(f"正在读取: {xlsx_path}")
    wb = openpyxl.load_workbook(str(xlsx_path), data_only=False)

    print(f"总sheet数: {len(wb.sheetnames)}")
    print(f"Sheet列表: {wb.sheetnames}")

    result = {
        "source_file": str(xlsx_path),
        "total_sheets": len(wb.sheetnames),
        "sheet_names": wb.sheetnames,
        "sheets": {},
        "confirmation": {
            "l5_5_amortization": None,
            "l5_3_unrecognized_detail": None,
        },
        "validations": {},
        "summary": {
            "total_formulas": 0,
            "sheets_with_formulas": [],
            "key_findings": [],
        }
    }

    # 逐sheet提取结构
    for name in wb.sheetnames:
        print(f"  处理: {name}")
        ws = wb[name]
        info = extract_sheet_structure(ws)
        result["sheets"][name] = info

        if info["formula_count"] > 0:
            result["summary"]["total_formulas"] += info["formula_count"]
            result["summary"]["sheets_with_formulas"].append({
                "name": name,
                "formula_count": info["formula_count"]
            })

    # 确认L5-5摊销测算表
    result["confirmation"]["l5_5_amortization"] = confirm_l5_5_amortization(wb)

    # 确认L5-3未确认融资费用明细表
    result["confirmation"]["l5_3_unrecognized_detail"] = confirm_l5_3_unrecognized_detail(wb)

    # 验证
    result["validations"] = {
        "total_sheets": len(wb.sheetnames),
        "expected_9_sheets": len(wb.sheetnames) >= 9,
        "l5_5_found": result["confirmation"]["l5_5_amortization"]["found"],
        "l5_3_found": result["confirmation"]["l5_3_unrecognized_detail"]["found"],
    }

    # 生成key findings
    findings = result["summary"]["key_findings"]
    findings.append(f"📊 总sheet数: {len(wb.sheetnames)}")
    findings.append(f"📊 总公式数: {result['summary']['total_formulas']}")

    # L5-5 findings
    if result["confirmation"]["l5_5_amortization"]["found"]:
        det = result["confirmation"]["l5_5_amortization"]["details"]
        findings.append(
            f"✅ L5-5摊销测算表已确认: "
            f"{result['confirmation']['l5_5_amortization']['sheet_name']} "
            f"({det['dims']})"
        )
        if det.get("has_initial_amount_col"):
            findings.append("  ✅ 含初始确认金额列")
        if det.get("has_eir_col"):
            findings.append("  ✅ 含实际利率列")
        if det.get("has_present_value_col"):
            findings.append("  ✅ 含现值列")
        if det.get("has_amortization_col"):
            findings.append("  ✅ 含未确认融资费用/摊销列")
        if det.get("has_repayment_col"):
            findings.append("  ✅ 含付款/偿还列")
        if det.get("has_period_col"):
            findings.append("  ✅ 含年份/期数列")
        if det.get("has_end_cost_col"):
            findings.append("  ✅ 含余额/期末列")
        if det.get("has_difference_col"):
            findings.append("  ✅ 含差异列")
        findings.append(f"  📊 公式数: {det['formula_count']}")
        if det.get("column_structure"):
            findings.append(f"  📋 列结构: {json.dumps(det['column_structure'], ensure_ascii=False)[:200]}")
    else:
        findings.append("⚠️ 未找到L5-5摊销测算表")

    # L5-3 findings
    if result["confirmation"]["l5_3_unrecognized_detail"]["found"]:
        det = result["confirmation"]["l5_3_unrecognized_detail"]["details"]
        findings.append(
            f"✅ L5-3未确认融资费用明细已确认: "
            f"{result['confirmation']['l5_3_unrecognized_detail']['sheet_name']} "
            f"({det['dims']})"
        )
        if det.get("has_loan_item_col"):
            findings.append("  ✅ 含款项/项目列")
        if det.get("has_begin_balance_col"):
            findings.append("  ✅ 含期初余额列")
        if det.get("has_initial_unrecognized_col"):
            findings.append("  ✅ 含初始未确认列")
        if det.get("has_period_amortization_col"):
            findings.append("  ✅ 含本期摊销列")
        if det.get("has_cumulative_amortization_col"):
            findings.append("  ✅ 含累计摊销列")
        if det.get("has_balance_col"):
            findings.append("  ✅ 含余额/期末列")
        if det.get("has_increase_col"):
            findings.append("  ✅ 含增加列")
        if det.get("has_decrease_col"):
            findings.append("  ✅ 含减少/摊销列")
        findings.append(f"  📊 公式数: {det['formula_count']}")
        if det.get("column_structure"):
            findings.append(f"  📋 列结构: {json.dumps(det['column_structure'], ensure_ascii=False)[:200]}")
    else:
        findings.append("⚠️ 未找到L5-3未确认融资费用明细表")

    # 输出JSON
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n产出文件: {OUTPUT_PATH}")
    print(f"\n=== Key Findings ===")
    for finding in findings:
        print(f"  {finding}")

    wb.close()


if __name__ == "__main__":
    main()
