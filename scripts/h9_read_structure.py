"""
Phase 0.1: openpyxl脚本读取H9租赁负债.xlsx全部sheet
提取结构 + 确认摊销表sheet结构
产出：h9_structure_summary.json
"""

import json
import re
from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter

# Path to the H9 xlsx template
XLSX_PATH = Path(r"d:\GT_plan\基础数据\致同通用审计程序及底稿模板（2025年修订）\1.致同审计程序及底稿模板（2025年）\4.风险应对-实质性程序（D-N）\H 固定资产循环\H9 租赁负债.xlsx")

# Output path
OUTPUT_PATH = Path(r"d:\GT_plan\.kiro\specs\h9-lease-liabilities\h9_structure_summary.json")


def extract_cell_value(cell):
    """Extract cell value, handling merged cells and formulas."""
    if cell.value is None:
        return None
    return str(cell.value)


def is_formula(value):
    """Check if a cell value is a formula."""
    if value and isinstance(value, str) and value.startswith("="):
        return True
    return False


def extract_sheet_structure(ws, sheet_name: str) -> dict:
    """Extract structure from a single worksheet."""
    result = {
        "sheet_name": sheet_name,
        "dimensions": ws.dimensions,
        "max_row": ws.max_row,
        "max_column": ws.max_column,
        "merged_cells": [str(mc) for mc in ws.merged_cells.ranges],
        "headers": [],
        "column_widths": {},
        "formulas": [],
        "sample_data": [],
        "key_patterns": [],
    }

    # Extract first few rows as headers/structure
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
            result["column_widths"][col_letter] = dim.width

    # Scan for formulas (first 50 rows)
    scan_rows = min(50, ws.max_row) if ws.max_row else 0
    for row_idx in range(1, scan_rows + 1):
        for col_idx in range(1, (ws.max_column or 0) + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            val = extract_cell_value(cell)
            if is_formula(val):
                col_letter = get_column_letter(col_idx)
                result["formulas"].append({
                    "cell": f"{col_letter}{row_idx}",
                    "formula": val,
                })

    # Sample data rows (rows 6-15 or available)
    start_sample = 6
    end_sample = min(15, ws.max_row) if ws.max_row else 0
    for row_idx in range(start_sample, end_sample + 1):
        row_data = []
        for col_idx in range(1, (ws.max_column or 0) + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            val = extract_cell_value(cell)
            row_data.append(val)
        result["sample_data"].append({"row": row_idx, "values": row_data})

    # Identify key patterns
    if ws.max_row and ws.max_row > 0:
        # Check for subtotal/summary rows
        for row_idx in range(1, min(ws.max_row + 1, 100)):
            cell_a = ws.cell(row=row_idx, column=1)
            val = extract_cell_value(cell_a)
            if val and any(kw in str(val) for kw in ["合计", "小计", "总计", "净额"]):
                result["key_patterns"].append({
                    "type": "summary_row",
                    "row": row_idx,
                    "label": val,
                })

    return result


def analyze_amortization_sheet(ws, sheet_name: str) -> dict:
    """Deep analysis of the amortization sheet (H9-4)."""
    analysis = {
        "is_amortization": True,
        "column_structure": [],
        "formula_patterns": {},
        "row_structure": {
            "header_row": None,
            "data_start_row": None,
            "total_periods_found": 0,
        },
    }

    # Find the header row with key column labels
    amort_keywords = ["期数", "期初", "租金", "利息", "本金", "期末", "余额", "偿还"]
    for row_idx in range(1, min(10, (ws.max_row or 0) + 1)):
        row_values = []
        for col_idx in range(1, (ws.max_column or 0) + 1):
            val = extract_cell_value(ws.cell(row=row_idx, column=col_idx))
            row_values.append(val)
        
        # Check if this row contains amortization headers
        row_text = " ".join([v for v in row_values if v])
        if any(kw in row_text for kw in amort_keywords):
            analysis["row_structure"]["header_row"] = row_idx
            analysis["column_structure"] = row_values
            analysis["row_structure"]["data_start_row"] = row_idx + 1
            break

    # Count data rows (periods)
    if analysis["row_structure"]["data_start_row"]:
        start = analysis["row_structure"]["data_start_row"]
        period_count = 0
        for row_idx in range(start, (ws.max_row or 0) + 1):
            first_cell = extract_cell_value(ws.cell(row=row_idx, column=1))
            if first_cell and (first_cell.isdigit() or "期" in str(first_cell)):
                period_count += 1
            elif first_cell and any(kw in str(first_cell) for kw in ["合计", "总计"]):
                break
        analysis["row_structure"]["total_periods_found"] = period_count

    # Analyze formula patterns in data rows
    if analysis["row_structure"]["data_start_row"]:
        data_row = analysis["row_structure"]["data_start_row"]
        for col_idx in range(1, (ws.max_column or 0) + 1):
            cell = ws.cell(row=data_row, column=col_idx)
            val = extract_cell_value(cell)
            col_letter = get_column_letter(col_idx)
            if is_formula(val):
                analysis["formula_patterns"][col_letter] = val

    return analysis


def main():
    print(f"Reading: {XLSX_PATH}")
    print(f"File exists: {XLSX_PATH.exists()}")

    # Load workbook with data_only=False to see formulas
    wb = openpyxl.load_workbook(str(XLSX_PATH), data_only=False, read_only=False)

    summary = {
        "file_path": str(XLSX_PATH),
        "total_sheets": len(wb.sheetnames),
        "sheet_names": wb.sheetnames,
        "sheets": {},
        "overview": {
            "description": "H9租赁负债底稿模板结构分析",
            "subject_code": "2205",
            "subject_name": "租赁负债(贷方/负债类) + 未确认融资费用(借方/负债备抵类)",
            "standard": "CAS21 新租赁准则",
            "paired_with": "H8 使用权资产",
            "key_characteristic": "负债类贷方科目：期末=期初+贷方-借方；未确认融资费用是借方备抵",
        },
    }

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        print(f"\nProcessing sheet: {sheet_name}")
        print(f"  Dimensions: {ws.dimensions}, Rows: {ws.max_row}, Cols: {ws.max_column}")

        # Extract general structure
        sheet_info = extract_sheet_structure(ws, sheet_name)
        summary["sheets"][sheet_name] = sheet_info

        # Note: H9-4 in the xlsx is "调整分录汇总" (Adjustment), NOT amortization.
        # No dedicated amortization sheet exists in this workbook.
        # The amortization schedule will be a computed/generated view in the frontend.

    # Generate sheet purpose mapping (corrected based on actual content)
    sheet_purposes = {}
    for name in wb.sheetnames:
        purpose = "未确定"
        name_lower = name.lower()
        if "目录" in name:
            purpose = "底稿目录(Tab_Index)"
        elif "H9A" in name or ("程序" in name and "实质性" in name):
            purpose = "实质性程序表(Procedure_Table_H9A)"
        elif "H9-1" in name or "审定" in name:
            purpose = "审定表(Adjudication_H9_1) - 科目2205+未确认融资费用"
        elif "附注" in name and "上市" in name:
            purpose = "附注披露-上市公司(Disclosure_Listed)"
        elif "附注" in name and ("国" in name or "SOE" in name_lower):
            purpose = "附注披露-国企(Disclosure_SOE)"
        elif "H9-2" in name and "租赁负债" in name:
            purpose = "租赁负债明细表(Detail_H9_2) - 22列按合同列示(含借贷/调整/到期分析/关联/发函)"
        elif "H9-3" in name or "未确认融资费用" in name:
            purpose = "未确认融资费用明细表(Finance_Cost_H9_3) - 21列(与H9-2出租方联动)"
        elif "H9-4" in name and "调整" in name:
            purpose = "调整分录汇总(Adjustment_H9_4) - 10列(调整事项/类别/科目/借贷)"
        elif "GT_Custom" in name:
            purpose = "自定义配置(GT_Custom) - 系统预留"
        elif "附注" in name:
            purpose = "附注披露(Disclosure)"
        sheet_purposes[name] = purpose

    summary["sheet_purposes"] = sheet_purposes

    # KEY FINDINGS - spec vs actual xlsx divergence
    summary["key_findings"] = {
        "total_effective_sheets": 8,  # 9 - GT_Custom = 8 effective
        "spec_vs_actual_divergence": {
            "H9-4_is_NOT_amortization": True,
            "H9-4_actual_content": "调整分录汇总表 (Adjustment Entries Summary, 10 columns)",
            "spec_expected_H9-4": "摊销表 (Amortization Schedule)",
            "no_dedicated_amortization_sheet": True,
            "resolution": "摊销表(amortization)将作为前端计算生成的功能视图，非xlsx源模板原生sheet。基于H9-2明细表的利率+期限数据动态生成每笔合同的摊销计划。",
        },
        "no_H9-5_H9-6_sheets": {
            "description": "源模板无H9-5(关联交易检查表)和H9-6独立sheet",
            "H9-2_includes_related_party": "H9-2第19列(S列)'是否关联方'已涵盖关联方信息",
            "H9-2_includes_confirmation": "H9-2第20列(T列)'发函或替代情况'已涵盖函证",
            "resolution": "关联交易检查功能可嵌入H9-2或作为前端衍生视图",
        },
        "sheet_encoding_correction": {
            "H9-4_in_xlsx": "调整分录汇总(非摊销表)",
            "spec_numbering_needs_update": "原spec认为H9-4=摊销/H9-5=调整/H9-6=关联。实际H9只到H9-4，且H9-4=调整。摊销和关联无独立sheet。",
        },
        "formula_count_estimate": {
            "审定表H9-1": "~80 formulas (13列×34行, 复杂变动率IF公式)",
            "明细表H9-2": "~60 formulas (22列, 期末=期初-借+贷, SUM合计)",
            "融资费用H9-3": "~55 formulas (21列, 跨sheet引用H9-2, 复杂借贷+调整)",
            "调整分录H9-4": "~6 formulas (仅表头引用底稿目录)",
            "total_estimated": "~200+ formulas",
        },
    }

    # H9-1 审定表结构确认
    summary["adjudication_h9_1_structure"] = {
        "dimensions": "A1:M34, 13列×34行",
        "sections": [
            {"name": "一、租赁负债原值", "rows": "7-11", "items": "项目A/B/…+合计", "note": "贷方科目！期末=期初+贷方-借方"},
            {"name": "二、未确认融资费用", "rows": "12-16", "items": "项目A/B/…+合计", "note": "借方备抵！"},
            {"name": "三、租赁负债净额(原值-融资费用)", "rows": "17-21", "items": "差额计算", "note": "row18=row8-row13"},
            {"name": "四、审计比较", "rows": "22-23", "note": "审定vs报表差额"},
            {"name": "五、审计说明/结论", "rows": "31-34"},
        ],
        "columns": {
            "A": "项目",
            "B": "期初-未审数",
            "C": "期初-账项调整",
            "D": "期初-审定数(=B+C)",
            "E": "期初-重分类(减一年内到期)",
            "F": "期初-报表数(=D-E)",
            "G": "期末-未审数",
            "H": "期末-账项调整",
            "I": "期末-审定数(=G+H)",
            "J": "期末-重分类(减一年内到期)",
            "K": "期末-报表数(=I-J)",
            "L": "变动额(=K-F)",
            "M": "变动率(IF复杂公式)",
        },
        "key_formulas": {
            "审定数": "D=B+C / I=G+H",
            "报表数": "F=D-E / K=I-J",
            "变动额": "L=K-F",
            "变动率": "M=IF(AND(F=0,L=0),0,IF(AND(F=0,L>0),1,L/F))",
            "净额": "B18=B8-B13 (原值-融资费用)",
            "合计": "SUM(range)",
        },
    }

    # H9-2 明细表结构确认
    summary["detail_h9_2_structure"] = {
        "dimensions": "A1:V26, 22列×26行",
        "header_rows": "7-8 (双行表头，合并单元格)",
        "data_rows": "9-13 (5笔合同示例)",
        "total_row": 14,
        "columns": {
            "A": "出租方名称",
            "B": "期初余额",
            "C": "未审-借方发生",
            "D": "未审-贷方发生",
            "E": "未审-期末余额(=B-C+D, 负债贷方！)",
            "F": "期初调整",
            "G": "本期调整-借方发生",
            "H": "本期调整-贷方发生",
            "I": "审定-期初余额(=B+F)",
            "J": "审定-借方发生(=C+G)",
            "K": "审定-贷方发生(=D+H)",
            "L": "审定-期末余额(=I-J+K, 负债贷方！)",
            "M": "重分类：减一年内到期",
            "N": "期末报表数(=L-M)",
            "O": "到期日-1年以下",
            "P": "到期日-1~2年",
            "Q": "到期日-2~3年",
            "R": "到期日-3年以上",
            "S": "是否关联方",
            "T": "发函或替代情况",
            "U": "期后付款",
            "V": "备注",
        },
        "key_formulas": {
            "期末余额_负债类": "E=B-C+D (期初-借方+贷方, 贷方科目!)",
            "审定期初": "I=B+F",
            "审定借方": "J=C+G",
            "审定贷方": "K=D+H",
            "审定期末": "L=I-J+K (贷方!)",
            "报表数": "N=L-M",
        },
    }

    # H9-3 融资费用明细结构确认
    summary["finance_cost_h9_3_structure"] = {
        "dimensions": "A1:U27, 21列×27行",
        "header_rows": "7-8 (双行表头)",
        "data_rows": "9-13 (与H9-2出租方联动)",
        "total_row": 14,
        "cross_sheet_ref": "A列引用 '租赁负债明细表H9-2'!A9~A13 (出租方名称自动同步)",
        "columns": {
            "A": "出租方名称(=H9-2!A列)",
            "B": "期初余额",
            "C": "未审-借方发生",
            "D": "未审-贷方发生",
            "E": "未审-期末余额(=B+C-D, 借方备抵!)",
            "F": "账项调整-借方",
            "G": "账项调整-贷方",
            "H": "重分类调整-借方",
            "I": "重分类调整-贷方",
            "J": "审定-期初余额(=B)",
            "K": "审定-借方发生(=C+F+H)",
            "L": "审定-贷方发生(=D+G+I)",
            "M": "审定-期末余额(=J+K-L, 借方备抵!)",
            "N": "减：期末一年内到期未确认融资费用",
            "O": "期末最终审定数(=M-N)",
            "P": "到期日-1年以下",
            "Q": "到期日-1~2年",
            "R": "到期日-2~3年",
            "S": "到期日-3年以上",
            "T": "是否是关联方",
            "U": "备注",
        },
        "key_formulas": {
            "期末_借方备抵": "E=B+C-D (借方科目! 期初+借-贷)",
            "审定期初": "J=B",
            "审定借方": "K=C+F+H (全部借方合并)",
            "审定贷方": "L=D+G+I (全部贷方合并)",
            "审定期末_借方": "M=J+K-L (备抵借方!)",
            "最终审定": "O=M-N",
        },
        "note": "未确认融资费用是借方/负债备抵类(与H9-2相反)。期末=期初+借-贷。",
    }

    # Write output
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"Summary written to: {OUTPUT_PATH}")
    print(f"Total sheets: {summary['total_sheets']}")
    print(f"Sheet names: {summary['sheet_names']}")
    print(f"\nSheet purposes:")
    for name, purpose in sheet_purposes.items():
        print(f"  {name}: {purpose}")

    print(f"\n*** KEY FINDINGS ***")
    print(f"  1. H9-4 is '调整分录汇总' (Adjustment), NOT '摊销表' (Amortization)")
    print(f"  2. No dedicated amortization sheet exists in this workbook")
    print(f"  3. Amortization schedule → computed/generated view in frontend")
    print(f"  4. No H9-5/H9-6 sheets (关联方 info embedded in H9-2 col S/T)")
    print(f"  5. H9-3 references H9-2 via cross-sheet formula (出租方名称联动)")
    print(f"  6. Effective sheets: 8 (9 - GT_Custom)")
    print(f"  7. Estimated formulas: ~200+")
    print(f"  8. H9-1 has 3 sections: 原值(贷方)+未确认融资费用(借方)+净额")


if __name__ == "__main__":
    main()
