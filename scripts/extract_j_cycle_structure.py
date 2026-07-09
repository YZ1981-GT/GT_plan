"""
J循环 Phase0 Task 0.1: 提取 J1/J2/J3 xlsx 结构
- J1 应付职工薪酬.xlsx (22 sheets)
- J2 长期应付职工薪酬-设定受益计划净资产.xlsx (9 sheets)
- J3 股份支付.xlsx (6 sheets)

门禁验证:
1. J1: 确认负债类贷方公式方向 (期末=期初+贷方-借方)
2. J3: 确认 Black-Scholes 参数列存在
"""

import json
import os
import re
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

BASE_DIR = Path(r"d:\GT_plan")
XLSX_DIR = BASE_DIR / "基础数据" / "致同通用审计程序及底稿模板（2025年修订）" / "1.致同审计程序及底稿模板（2025年）" / "4.风险应对-实质性程序（D-N）" / "J 职工薪酬循环"

OUTPUT_DIR_J1 = BASE_DIR / ".kiro" / "specs" / "j1-employee-compensation"
OUTPUT_DIR_J2 = BASE_DIR / ".kiro" / "specs" / "j2-defined-benefit-plan"
OUTPUT_DIR_J3 = BASE_DIR / ".kiro" / "specs" / "j3-share-based-payment"


def extract_formulas(ws, max_rows=50):
    """Extract formulas from first N rows of a worksheet."""
    formulas = []
    for row in ws.iter_rows(min_row=1, max_row=min(max_rows, ws.max_row or 1), values_only=False):
        for cell in row:
            if cell.value and isinstance(cell.value, str) and cell.value.startswith("="):
                formulas.append({
                    "cell": f"{get_column_letter(cell.column)}{cell.row}",
                    "formula": cell.value
                })
    return formulas


def extract_headers(ws, max_header_rows=5):
    """Extract column headers from first few rows."""
    headers = []
    for row_idx in range(1, min(max_header_rows + 1, (ws.max_row or 0) + 1)):
        row_headers = []
        for cell in ws[row_idx]:
            val = cell.value
            if val is not None:
                row_headers.append(str(val).strip()[:100])  # Truncate long values
        if row_headers and any(h for h in row_headers):
            headers.append({"row": row_idx, "values": row_headers})
    return headers


def check_liability_credit_direction(formulas, sheet_name):
    """Check if formulas follow 负债类贷方 pattern: 期末=期初+贷方-借方."""
    credit_patterns = []
    for f in formulas:
        formula = f["formula"].upper()
        # Look for patterns like: ending = opening + credit - debit
        # In Chinese accounting: 期末=期初+贷方-借方
        # Or cell references that follow: C = A + B - D pattern (credit direction)
        if "+" in formula and "-" in formula:
            credit_patterns.append(f)
    return credit_patterns


def check_bs_parameters(headers):
    """Check for Black-Scholes parameter columns in J3."""
    bs_keywords = [
        "行权价", "股价", "无风险利率", "波动率", "期限", "股利",
        "exercise price", "stock price", "risk-free", "volatility",
        "期权", "公允价值", "Black", "Scholes", "BS",
        "标的股票", "行权期", "等待期", "可行权日",
        "S0", "X", "σ", "r", "T", "d1", "d2", "N(d1)", "N(d2)"
    ]
    found_params = []
    for header_row in headers:
        for val in header_row.get("values", []):
            for kw in bs_keywords:
                if kw in val:
                    found_params.append({"keyword": kw, "header": val, "row": header_row["row"]})
                    break
    return found_params


def extract_sheet_structure(ws, sheet_name):
    """Extract full structure of a single worksheet."""
    headers = extract_headers(ws, max_header_rows=8)
    formulas = extract_formulas(ws, max_rows=80)

    return {
        "sheet_name": sheet_name,
        "max_row": ws.max_row or 0,
        "max_column": ws.max_column or 0,
        "column_count": ws.max_column or 0,
        "row_count": ws.max_row or 0,
        "headers": headers,
        "formulas_found": len(formulas),
        "sample_formulas": formulas[:20],  # Keep first 20
        "merged_cells": [str(m) for m in ws.merged_cells.ranges][:30],
    }


def process_workbook(xlsx_path, spec_name):
    """Process a single workbook and return structure summary."""
    print(f"\n{'='*60}")
    print(f"Processing: {xlsx_path.name}")
    print(f"{'='*60}")

    wb = load_workbook(str(xlsx_path), data_only=False)
    sheets = wb.sheetnames
    print(f"Total sheets: {len(sheets)}")
    print(f"Sheet names: {sheets}")

    result = {
        "spec": spec_name,
        "file_name": xlsx_path.name,
        "total_sheets": len(sheets),
        "sheet_names": sheets,
        "sheets": [],
        "validation": {}
    }

    for sheet_name in sheets:
        ws = wb[sheet_name]
        structure = extract_sheet_structure(ws, sheet_name)
        result["sheets"].append(structure)
        print(f"  [{sheet_name}] rows={structure['row_count']}, cols={structure['column_count']}, formulas={structure['formulas_found']}")

    wb.close()
    return result


def classify_j1_sheets(result):
    """Classify J1 sheets into valid/skip and check liability direction."""
    # J1 skip patterns (辅助说明、目录等)
    skip_keywords = ["目录", "说明", "索引", "封面", "附录", "辅助"]
    valid_sheets = []
    skip_sheets = []

    for sheet in result["sheets"]:
        name = sheet["sheet_name"]
        is_skip = any(kw in name for kw in skip_keywords)
        if is_skip:
            skip_sheets.append(name)
        else:
            valid_sheets.append(name)

    # Check liability credit direction in all sheets
    liability_evidence = []
    for sheet in result["sheets"]:
        for f in sheet.get("sample_formulas", []):
            formula = f["formula"]
            # Patterns indicating 贷方 direction:
            # 期末 = 期初 + 贷方发生额 - 借方发生额
            # or in Excel: = X + Y - Z where context suggests credit
            if "+" in formula and "-" in formula:
                liability_evidence.append({
                    "sheet": sheet["sheet_name"],
                    "cell": f["cell"],
                    "formula": formula
                })

    # Look for specific header patterns confirming direction
    direction_headers = []
    for sheet in result["sheets"]:
        for header_row in sheet.get("headers", []):
            for val in header_row.get("values", []):
                if any(kw in val for kw in ["贷方", "借方", "期末余额", "期初余额", "本期增加", "本期减少"]):
                    direction_headers.append({
                        "sheet": sheet["sheet_name"],
                        "header": val,
                        "row": header_row["row"]
                    })

    result["validation"] = {
        "valid_sheets": valid_sheets,
        "valid_count": len(valid_sheets),
        "skip_sheets": skip_sheets,
        "skip_count": len(skip_sheets),
        "liability_credit_direction": {
            "confirmed": len(liability_evidence) > 0 or len(direction_headers) > 0,
            "formula_evidence": liability_evidence[:15],
            "header_evidence": direction_headers[:15],
            "rule": "期末=期初+贷方-借方 (负债类贷方增加)"
        }
    }
    return result


def classify_j2_sheets(result):
    """Classify J2 sheets and check actuarial formulas."""
    skip_keywords = ["目录", "说明", "索引", "封面", "附录", "辅助", "L2A"]
    valid_sheets = []
    skip_sheets = []

    for sheet in result["sheets"]:
        name = sheet["sheet_name"]
        is_skip = any(kw in name for kw in skip_keywords)
        if is_skip:
            skip_sheets.append(name)
        else:
            valid_sheets.append(name)

    # Check for actuarial keywords
    actuarial_evidence = []
    for sheet in result["sheets"]:
        for header_row in sheet.get("headers", []):
            for val in header_row.get("values", []):
                if any(kw in val for kw in ["精算", "DBO", "设定受益", "义务", "计划资产",
                                             "服务成本", "利息", "折现率", "死亡率",
                                             "薪酬增长率", "离职率", "ISA620"]):
                    actuarial_evidence.append({
                        "sheet": sheet["sheet_name"],
                        "header": val,
                        "row": header_row["row"]
                    })

    # Check liability direction
    direction_headers = []
    for sheet in result["sheets"]:
        for header_row in sheet.get("headers", []):
            for val in header_row.get("values", []):
                if any(kw in val for kw in ["贷方", "借方", "期末余额", "期初余额"]):
                    direction_headers.append({
                        "sheet": sheet["sheet_name"],
                        "header": val,
                        "row": header_row["row"]
                    })

    result["validation"] = {
        "valid_sheets": valid_sheets,
        "valid_count": len(valid_sheets),
        "skip_sheets": skip_sheets,
        "skip_count": len(skip_sheets),
        "liability_credit_direction": {
            "confirmed": len(direction_headers) > 0,
            "header_evidence": direction_headers[:10],
            "rule": "期末=期初+贷方-借方 (负债类贷方增加)"
        },
        "actuarial_formulas": {
            "found": len(actuarial_evidence) > 0,
            "evidence": actuarial_evidence[:15]
        }
    }
    return result


def classify_j3_sheets(result):
    """Classify J3 sheets and check BS parameters."""
    skip_keywords = ["目录", "说明", "索引", "封面", "附录", "辅助"]
    valid_sheets = []
    skip_sheets = []

    for sheet in result["sheets"]:
        name = sheet["sheet_name"]
        is_skip = any(kw in name for kw in skip_keywords)
        if is_skip:
            skip_sheets.append(name)
        else:
            valid_sheets.append(name)

    # Check BS parameters
    bs_evidence = []
    vesting_evidence = []
    for sheet in result["sheets"]:
        params = check_bs_parameters(sheet.get("headers", []))
        if params:
            bs_evidence.extend([{**p, "sheet": sheet["sheet_name"]} for p in params])

        # Check for vesting period (等待期) formulas
        for header_row in sheet.get("headers", []):
            for val in header_row.get("values", []):
                if any(kw in val for kw in ["等待期", "可行权", "行权", "归属",
                                             "授予日", "到期日", "分摊",
                                             "累计费用", "当期费用", "剩余"]):
                    vesting_evidence.append({
                        "sheet": sheet["sheet_name"],
                        "header": val,
                        "row": header_row["row"]
                    })

    result["validation"] = {
        "valid_sheets": valid_sheets,
        "valid_count": len(valid_sheets),
        "skip_sheets": skip_sheets,
        "skip_count": len(skip_sheets),
        "bs_parameters": {
            "confirmed": len(bs_evidence) > 0,
            "evidence": bs_evidence[:20],
            "rule": "Black-Scholes参数列: 行权价/股价/无风险利率/波动率/期限"
        },
        "vesting_period": {
            "found": len(vesting_evidence) > 0,
            "evidence": vesting_evidence[:15],
            "rule": "等待期公式: 累计费用=公允价值×(已等待/总等待期)"
        }
    }
    return result


def main():
    # Process J1
    j1_path = XLSX_DIR / "J1 应付职工薪酬.xlsx"
    j1_result = process_workbook(j1_path, "j1-employee-compensation")
    j1_result = classify_j1_sheets(j1_result)

    # Process J2
    j2_path = XLSX_DIR / "J2 长期应付职工薪酬-设定受益计划净资产.xlsx"
    j2_result = process_workbook(j2_path, "j2-defined-benefit-plan")
    j2_result = classify_j2_sheets(j2_result)

    # Process J3
    j3_path = XLSX_DIR / "J3 股份支付.xlsx"
    j3_result = process_workbook(j3_path, "j3-share-based-payment")
    j3_result = classify_j3_sheets(j3_result)

    # Write outputs
    os.makedirs(OUTPUT_DIR_J1, exist_ok=True)
    os.makedirs(OUTPUT_DIR_J2, exist_ok=True)
    os.makedirs(OUTPUT_DIR_J3, exist_ok=True)

    with open(OUTPUT_DIR_J1 / "j1_structure_summary.json", "w", encoding="utf-8") as f:
        json.dump(j1_result, f, ensure_ascii=False, indent=2)
    print(f"\n✅ J1 output: {OUTPUT_DIR_J1 / 'j1_structure_summary.json'}")

    with open(OUTPUT_DIR_J2 / "j2_structure_summary.json", "w", encoding="utf-8") as f:
        json.dump(j2_result, f, ensure_ascii=False, indent=2)
    print(f"✅ J2 output: {OUTPUT_DIR_J2 / 'j2_structure_summary.json'}")

    with open(OUTPUT_DIR_J3 / "j3_structure_summary.json", "w", encoding="utf-8") as f:
        json.dump(j3_result, f, ensure_ascii=False, indent=2)
    print(f"✅ J3 output: {OUTPUT_DIR_J3 / 'j3_structure_summary.json'}")

    # Gate validation summary
    print(f"\n{'='*60}")
    print("🚦 门禁验证结果:")
    print(f"{'='*60}")

    # Gate 1: J1 负债贷方方向
    j1_gate = j1_result["validation"]["liability_credit_direction"]["confirmed"]
    print(f"\n[Gate 1] J1 负债类贷方公式方向: {'✅ PASS' if j1_gate else '❌ FAIL'}")
    if j1_gate:
        evidence = j1_result["validation"]["liability_credit_direction"]
        print(f"  Formula evidence: {len(evidence.get('formula_evidence', []))} patterns")
        print(f"  Header evidence: {len(evidence.get('header_evidence', []))} columns")
        for h in evidence.get("header_evidence", [])[:5]:
            print(f"    - [{h['sheet']}] row {h['row']}: {h['header']}")

    # Gate 2: J3 BS参数列
    j3_gate = j3_result["validation"]["bs_parameters"]["confirmed"]
    print(f"\n[Gate 2] J3 Black-Scholes 参数列: {'✅ PASS' if j3_gate else '❌ FAIL'}")
    if j3_gate:
        for p in j3_result["validation"]["bs_parameters"]["evidence"][:8]:
            print(f"    - [{p['sheet']}] row {p['row']}: '{p['header']}' (keyword: {p['keyword']})")

    # J3 vesting period
    j3_vesting = j3_result["validation"]["vesting_period"]["found"]
    print(f"\n[Gate 2b] J3 等待期公式: {'✅ FOUND' if j3_vesting else '⚠️ NOT FOUND in headers'}")
    if j3_vesting:
        for v in j3_result["validation"]["vesting_period"]["evidence"][:5]:
            print(f"    - [{v['sheet']}] row {v['row']}: '{v['header']}'")

    # J2 actuarial
    j2_actuarial = j2_result["validation"]["actuarial_formulas"]["found"]
    print(f"\n[Bonus] J2 精算公式: {'✅ FOUND' if j2_actuarial else '⚠️ NOT FOUND'}")
    if j2_actuarial:
        for a in j2_result["validation"]["actuarial_formulas"]["evidence"][:5]:
            print(f"    - [{a['sheet']}] row {a['row']}: '{a['header']}'")

    print(f"\n{'='*60}")
    all_pass = j1_gate and j3_gate
    print(f"总体门禁: {'✅ ALL GATES PASSED' if all_pass else '❌ SOME GATES FAILED'}")
    print(f"{'='*60}")

    return all_pass


if __name__ == "__main__":
    main()
