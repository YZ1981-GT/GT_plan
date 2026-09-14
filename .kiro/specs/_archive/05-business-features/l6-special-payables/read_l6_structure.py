"""
Phase 0.1: openpyxl脚本读取L6专项应付款.xlsx全部8 sheet
提取结构 + 确认审定表L6-1(73公式)+明细表L6-2结构
产出：l6_structure_summary.json
"""

import json
from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter

# 源文件路径（致同2025修订版源模板）
XLSX_PATH = Path(
    r"d:\GT_plan\数据\致同通用审计程序及底稿模板（2025年修订）"
    r"\1.致同审计程序及底稿模板（2025年）"
    r"\4.风险应对-实质性程序（D-N）\L 债务循环\L6 专项应付款.xlsx"
)
OUTPUT_PATH = Path(r"d:\GT_plan\.kiro\specs\l6-special-payables\l6_structure_summary.json")


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
        for col_idx in range(1, min(ws.max_column + 1, 35)):
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


def confirm_l6_1_adjudication(wb):
    """确认L6-1审定表结构（核心！负债类贷方科目）"""
    confirmation = {
        "found": False,
        "sheet_name": None,
        "details": {},
    }

    for name in wb.sheetnames:
        if "L6-1" in name or ("审定" in name and "L6" in name):
            ws = wb[name]
            confirmation["found"] = True
            confirmation["sheet_name"] = name
            confirmation["details"] = {
                "rows": ws.max_row,
                "cols": ws.max_column,
                "dims": f"{ws.max_row}×{ws.max_column}",
                "all_headers": [],
                "has_project_col": False,
                "has_begin_balance_col": False,
                "has_credit_col": False,
                "has_debit_col": False,
                "has_end_balance_col": False,
                "has_unadjusted_col": False,
                "has_aje_col": False,
                "has_rje_col": False,
                "has_audited_col": False,
                "has_subtotal_row": False,
                "formula_count": 0,
                "formula_samples": [],
                "column_structure": {},
            }

            # 检查前12行header
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
                        if "项目" in val_str:
                            confirmation["details"]["has_project_col"] = True
                        if "期初" in val_str:
                            confirmation["details"]["has_begin_balance_col"] = True
                        if "贷方" in val_str or "拨入" in val_str:
                            confirmation["details"]["has_credit_col"] = True
                        if "借方" in val_str or "使用" in val_str or "结转" in val_str:
                            confirmation["details"]["has_debit_col"] = True
                        if "期末" in val_str:
                            confirmation["details"]["has_end_balance_col"] = True
                        if "未审" in val_str:
                            confirmation["details"]["has_unadjusted_col"] = True
                        if "账项调整" in val_str or "AJE" in val_str:
                            confirmation["details"]["has_aje_col"] = True
                        if "重分类" in val_str or "RJE" in val_str:
                            confirmation["details"]["has_rje_col"] = True
                        if "审定" in val_str:
                            confirmation["details"]["has_audited_col"] = True

            # 检查合计行
            for row_idx in range(1, ws.max_row + 1):
                val = ws.cell(row=row_idx, column=1).value
                if val and ("合计" in str(val) or "小计" in str(val)):
                    confirmation["details"]["has_subtotal_row"] = True
                    break

            # 提取列结构（第5-7行为表头区域）
            col_struct = {}
            for col_idx in range(1, ws.max_column + 1):
                col_key = get_column_letter(col_idx)
                headers_for_col = []
                for row_idx in range(4, min(8, ws.max_row + 1)):
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
                        if len(confirmation["details"]["formula_samples"]) < 15:
                            confirmation["details"]["formula_samples"].append({
                                "cell": f"{get_column_letter(cell.column)}{cell.row}",
                                "formula": cell.value[:200],
                            })
            break

    return confirmation


def confirm_l6_2_detail(wb):
    """确认L6-2明细表结构（按专项项目列示）"""
    confirmation = {
        "found": False,
        "sheet_name": None,
        "details": {},
    }

    for name in wb.sheetnames:
        if "L6-2" in name or ("明细" in name and "L6" in name):
            ws = wb[name]
            confirmation["found"] = True
            confirmation["sheet_name"] = name
            confirmation["details"] = {
                "rows": ws.max_row,
                "cols": ws.max_column,
                "dims": f"{ws.max_row}×{ws.max_column}",
                "all_headers": [],
                "has_project_name_col": False,
                "has_source_col": False,
                "has_approval_col": False,
                "has_purpose_col": False,
                "has_begin_balance_col": False,
                "has_credit_in_col": False,
                "has_debit_use_col": False,
                "has_end_balance_col": False,
                "has_carry_forward_col": False,
                "formula_count": 0,
                "formula_samples": [],
                "column_structure": {},
            }

            # 检查前12行header
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
                        if "项目" in val_str or "名称" in val_str:
                            confirmation["details"]["has_project_name_col"] = True
                        if "来源" in val_str or "拨款" in val_str:
                            confirmation["details"]["has_source_col"] = True
                        if "批文" in val_str or "批准" in val_str:
                            confirmation["details"]["has_approval_col"] = True
                        if "用途" in val_str:
                            confirmation["details"]["has_purpose_col"] = True
                        if "期初" in val_str:
                            confirmation["details"]["has_begin_balance_col"] = True
                        if "拨入" in val_str or "收到" in val_str or "贷方" in val_str:
                            confirmation["details"]["has_credit_in_col"] = True
                        if "使用" in val_str or "借方" in val_str:
                            confirmation["details"]["has_debit_use_col"] = True
                        if "期末" in val_str:
                            confirmation["details"]["has_end_balance_col"] = True
                        if "结转" in val_str or "转出" in val_str:
                            confirmation["details"]["has_carry_forward_col"] = True

            # 提取列结构（第5-8行为表头区域）
            col_struct = {}
            for col_idx in range(1, ws.max_column + 1):
                col_key = get_column_letter(col_idx)
                headers_for_col = []
                for row_idx in range(4, min(10, ws.max_row + 1)):
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
                        if len(confirmation["details"]["formula_samples"]) < 15:
                            confirmation["details"]["formula_samples"].append({
                                "cell": f"{get_column_letter(cell.column)}{cell.row}",
                                "formula": cell.value[:200],
                            })
            break

    return confirmation


def main():
    if not XLSX_PATH.exists():
        # 尝试备选路径
        alt_path = Path(r"d:\GT_plan\backend\wp_templates\L\L6 专项应付款.xlsx")
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
            "l6_1_adjudication": None,
            "l6_2_detail": None,
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

    # 确认L6-1审定表
    result["confirmation"]["l6_1_adjudication"] = confirm_l6_1_adjudication(wb)

    # 确认L6-2明细表
    result["confirmation"]["l6_2_detail"] = confirm_l6_2_detail(wb)

    # 验证
    l6_1_formulas = result["confirmation"]["l6_1_adjudication"]["details"].get("formula_count", 0) if result["confirmation"]["l6_1_adjudication"]["found"] else 0
    result["validations"] = {
        "total_sheets": len(wb.sheetnames),
        "expected_8_sheets": len(wb.sheetnames) >= 8,
        "l6_1_found": result["confirmation"]["l6_1_adjudication"]["found"],
        "l6_1_formula_count": l6_1_formulas,
        "l6_1_expected_73_formulas": abs(l6_1_formulas - 73) <= 10,
        "l6_2_found": result["confirmation"]["l6_2_detail"]["found"],
        "l6_2_dims": result["confirmation"]["l6_2_detail"]["details"].get("dims", "N/A") if result["confirmation"]["l6_2_detail"]["found"] else "N/A",
        "account_code": "2601",
        "account_direction": "贷方/负债类",
        "formula": "期末=期初+贷方-借方",
    }

    # 生成key findings
    findings = result["summary"]["key_findings"]
    findings.append(f"📊 总sheet数: {len(wb.sheetnames)}")
    findings.append(f"📊 总公式数: {result['summary']['total_formulas']}")
    findings.append(f"📊 科目: 2601专项应付款（贷方/负债类）")
    findings.append(f"📊 公式铁律: 期末=期初+贷方-借方")

    # L6-1 findings
    if result["confirmation"]["l6_1_adjudication"]["found"]:
        det = result["confirmation"]["l6_1_adjudication"]["details"]
        findings.append(
            f"✅ L6-1审定表已确认: "
            f"{result['confirmation']['l6_1_adjudication']['sheet_name']} "
            f"({det['dims']})"
        )
        findings.append(f"  📊 公式数: {det['formula_count']} (预期~73)")
        if det.get("has_project_col"):
            findings.append("  ✅ 含项目列")
        if det.get("has_begin_balance_col"):
            findings.append("  ✅ 含期初列")
        if det.get("has_credit_col"):
            findings.append("  ✅ 含贷方/拨入列")
        if det.get("has_debit_col"):
            findings.append("  ✅ 含借方/使用列")
        if det.get("has_end_balance_col"):
            findings.append("  ✅ 含期末列")
        if det.get("has_unadjusted_col"):
            findings.append("  ✅ 含未审数列")
        if det.get("has_aje_col"):
            findings.append("  ✅ 含账项调整列")
        if det.get("has_rje_col"):
            findings.append("  ✅ 含重分类调整列")
        if det.get("has_audited_col"):
            findings.append("  ✅ 含审定数列")
        if det.get("has_subtotal_row"):
            findings.append("  ✅ 含合计/小计行")
    else:
        findings.append("⚠️ 未找到L6-1审定表")

    # L6-2 findings
    if result["confirmation"]["l6_2_detail"]["found"]:
        det = result["confirmation"]["l6_2_detail"]["details"]
        findings.append(
            f"✅ L6-2明细表已确认: "
            f"{result['confirmation']['l6_2_detail']['sheet_name']} "
            f"({det['dims']})"
        )
        findings.append(f"  📊 公式数: {det['formula_count']}")
        if det.get("has_project_name_col"):
            findings.append("  ✅ 含专项项目列")
        if det.get("has_source_col"):
            findings.append("  ✅ 含拨款来源列")
        if det.get("has_approval_col"):
            findings.append("  ✅ 含批文号列")
        if det.get("has_purpose_col"):
            findings.append("  ✅ 含用途列")
        if det.get("has_begin_balance_col"):
            findings.append("  ✅ 含期初余额列")
        if det.get("has_credit_in_col"):
            findings.append("  ✅ 含本期拨入列")
        if det.get("has_debit_use_col"):
            findings.append("  ✅ 含本期使用列")
        if det.get("has_carry_forward_col"):
            findings.append("  ✅ 含本期结转列")
        if det.get("has_end_balance_col"):
            findings.append("  ✅ 含期末余额列")
    else:
        findings.append("⚠️ 未找到L6-2明细表")

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
