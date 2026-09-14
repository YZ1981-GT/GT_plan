"""
Phase 0 Task 0.1: openpyxl脚本读取L4应付债券.xlsx全部15 sheet
提取结构 + 确认:
  - L4-2（89列极宽表）
  - L4-7A/B后续计量2分支
  - L4-8A/B账面核对2分支
  - L4-5权益划分
产出：l4_structure_summary.json
"""

import json
import os
from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter

# 源xlsx路径（优先用wp_templates副本，较稳定）
XLSX_PATHS = [
    Path(r"d:\GT_plan\backend\wp_templates\L\L4 应付债券.xlsx"),
    Path(r"d:\GT_plan\数据\致同通用审计程序及底稿模板（2025年修订）\1.致同审计程序及底稿模板（2025年）\4.风险应对-实质性程序（D-N）\L 债务循环\L4 应付债券.xlsx"),
]

OUTPUT_PATH = Path(r"d:\GT_plan\.kiro\specs\l4-bonds-payable\l4_structure_summary.json")


def find_xlsx():
    for p in XLSX_PATHS:
        if p.exists():
            return p
    raise FileNotFoundError(f"无法找到L4 应付债券.xlsx，已尝试路径: {XLSX_PATHS}")


def extract_headers(ws, max_row=5):
    """提取前几行作为表头候选（跳过空行）"""
    headers = []
    for row_idx in range(1, max_row + 1):
        row_data = []
        for col_idx in range(1, ws.max_column + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            val = cell.value
            if val is not None:
                row_data.append({"col": col_idx, "col_letter": get_column_letter(col_idx), "value": str(val)[:80]})
        if row_data:
            headers.append({"row": row_idx, "cells": row_data})
    return headers


def count_formulas(ws):
    """统计公式单元格数量"""
    formula_count = 0
    formula_samples = []
    for row in ws.iter_rows():
        for cell in row:
            if cell.data_type == 'f' or (isinstance(cell.value, str) and cell.value.startswith('=')):
                formula_count += 1
                if len(formula_samples) < 5:
                    formula_samples.append({
                        "cell": f"{get_column_letter(cell.column)}{cell.row}",
                        "formula": str(cell.value)[:100]
                    })
    return formula_count, formula_samples


def count_merged_cells(ws):
    """统计合并单元格"""
    return len(ws.merged_cells.ranges)


def extract_sheet_info(ws, sheet_name):
    """提取单个sheet的结构信息"""
    max_row = ws.max_row or 0
    max_col = ws.max_column or 0
    
    # 提取表头
    headers = extract_headers(ws, max_row=min(5, max_row))
    
    # 统计公式
    formula_count, formula_samples = count_formulas(ws)
    
    # 统计合并单元格
    merged_count = count_merged_cells(ws)
    
    # 提取第一列内容（通常是行标题/项目名）
    first_col_values = []
    for row_idx in range(1, min(max_row + 1, 70)):
        val = ws.cell(row=row_idx, column=1).value
        if val is not None:
            first_col_values.append({"row": row_idx, "value": str(val)[:60]})
    
    return {
        "sheet_name": sheet_name,
        "dimensions": f"{max_row}×{max_col}",
        "max_row": max_row,
        "max_column": max_col,
        "formula_count": formula_count,
        "formula_samples": formula_samples,
        "merged_cells_count": merged_count,
        "headers": headers,
        "first_column_sample": first_col_values[:30],
    }


def validate_structure(sheets_info):
    """验证关键结构"""
    validations = {
        "L4-2_has_89_columns": False,
        "L4-7A_exists_bullet": False,
        "L4-7B_exists_installment": False,
        "L4-8A_exists_bullet": False,
        "L4-8B_exists_installment": False,
        "L4-5_equity_liability_check": False,
        "total_sheets": len(sheets_info),
    }
    
    details = {}
    
    for info in sheets_info:
        name = info["sheet_name"]
        
        # L4-2 确认89列（精确匹配"L4-2"而非泛匹配"明细"）
        if "L4-2" in name:
            validations["L4-2_has_89_columns"] = info["max_column"] >= 85  # 允许±4列误差
            details["L4-2"] = {
                "actual_columns": info["max_column"],
                "confirmed_wide_table": info["max_column"] >= 85,
                "note": f"实际列数={info['max_column']}，{'✅确认极宽表' if info['max_column'] >= 85 else '⚠️列数不符'}"
            }
        
        # L4-7A/B 后续计量2分支
        if "到期一次还本付息" in name and "后续" in name:
            validations["L4-7A_exists_bullet"] = True
            details["L4-7A"] = {"sheet_name": name, "dims": info["dimensions"]}
        if "分期付息" in name and "后续" in name:
            validations["L4-7B_exists_installment"] = True
            details["L4-7B"] = {"sheet_name": name, "dims": info["dimensions"]}
        
        # L4-8A/B 账面核对2分支
        if "到期一次还本付息" in name and "账面" in name:
            validations["L4-8A_exists_bullet"] = True
            details["L4-8A"] = {"sheet_name": name, "dims": info["dimensions"]}
        if "分期付息" in name and "账面" in name:
            validations["L4-8B_exists_installment"] = True
            details["L4-8B"] = {"sheet_name": name, "dims": info["dimensions"]}
        
        # L4-5 权益划分
        if "权益" in name or "划分" in name:
            validations["L4-5_equity_liability_check"] = True
            details["L4-5"] = {"sheet_name": name, "dims": info["dimensions"]}
    
    return validations, details


def main():
    xlsx_path = find_xlsx()
    print(f"📂 读取: {xlsx_path}")
    
    wb = openpyxl.load_workbook(str(xlsx_path), data_only=False, read_only=False)
    
    print(f"📋 Sheet数量: {len(wb.sheetnames)}")
    print(f"📋 Sheet列表: {wb.sheetnames}")
    
    sheets_info = []
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        info = extract_sheet_info(ws, sheet_name)
        sheets_info.append(info)
        print(f"  ✓ {sheet_name}: {info['dimensions']} (公式:{info['formula_count']}, 合并:{info['merged_cells_count']})")
    
    all_sheet_names = list(wb.sheetnames)
    wb.close()
    
    # 验证关键结构
    validations, details = validate_structure(sheets_info)
    
    print("\n🔍 结构验证:")
    for k, v in validations.items():
        status = "✅" if v else "❌"
        print(f"  {status} {k}: {v}")
    
    if details:
        print("\n📐 关键sheet详情:")
        for k, v in details.items():
            print(f"  {k}: {v}")
    
    # 构建最终输出
    summary = {
        "source_file": str(xlsx_path),
        "total_sheets": len(sheets_info),
        "sheet_names": all_sheet_names,
        "validations": validations,
        "validation_details": details,
        "sheets": sheets_info,
    }
    
    # 写出JSON
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 产出: {OUTPUT_PATH}")
    
    # 最终确认
    all_pass = all(v for k, v in validations.items() if k != "total_sheets")
    if all_pass:
        print("🎉 全部验证通过！L4-2(89列)+L4-7A/B(2分支)+L4-8A/B(2分支)+L4-5(权益划分) 结构确认")
    else:
        failed = [k for k, v in validations.items() if not v and k != "total_sheets"]
        print(f"⚠️ 未通过验证项: {failed}")


if __name__ == "__main__":
    main()
