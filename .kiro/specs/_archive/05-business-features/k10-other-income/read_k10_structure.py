"""
Phase0 Task 0.1: openpyxl脚本读取K10其他收益.xlsx全部10 sheet
产出: k10_structure_summary.json
确认: K10-1 69公式 / K10-2 11公式
"""
import json
import os
from pathlib import Path

import openpyxl

# 源模板路径
XLSX_PATH = Path(r"d:\GT_plan\基础数据\致同通用审计程序及底稿模板（2025年修订）\1.致同审计程序及底稿模板（2025年）\4.风险应对-实质性程序（D-N）\K 管理循环\K10 其他收益.xlsx")

OUTPUT_DIR = Path(r"d:\GT_plan\.kiro\specs\k10-other-income")
OUTPUT_FILE = OUTPUT_DIR / "k10_structure_summary.json"


def count_formulas(ws):
    """统计sheet中公式单元格数量，区分header引用和业务公式"""
    total_count = 0
    header_ref_count = 0  # 引用底稿目录的表头公式
    business_count = 0    # 业务计算公式
    formula_cells = []
    business_formulas = []
    
    for row in ws.iter_rows():
        for cell in row:
            if cell.value and isinstance(cell.value, str) and cell.value.startswith("="):
                total_count += 1
                cell_ref = f"{cell.column_letter}{cell.row}"
                formula_str = cell.value
                
                # 区分header引用 vs 业务公式
                if "底稿目录!" in formula_str:
                    header_ref_count += 1
                else:
                    business_count += 1
                    business_formulas.append({
                        "cell": cell_ref,
                        "formula": formula_str[:100]
                    })
                
                formula_cells.append({
                    "cell": cell_ref,
                    "formula": formula_str[:100]
                })
    
    return {
        "total": total_count,
        "header_ref": header_ref_count,
        "business": business_count,
        "all_formulas": formula_cells,
        "business_formulas": business_formulas
    }


def get_column_names(ws, header_row=1):
    """获取列名（指定行）"""
    cols = []
    for cell in ws[header_row]:
        if cell.value is not None:
            cols.append(str(cell.value).strip())
    return cols


def find_header_row(ws, max_scan=10):
    """扫描前N行找到列头行（非空列数最多的行）"""
    best_row = 1
    best_count = 0
    results = {}
    for r in range(1, min(max_scan + 1, ws.max_row + 1)):
        cols = []
        for cell in ws[r]:
            if cell.value is not None:
                cols.append(str(cell.value).strip())
        if len(cols) > best_count:
            best_count = len(cols)
            best_row = r
        if cols:
            results[r] = cols
    return best_row, results.get(best_row, []), results


def get_sheet_dimensions(ws):
    """获取sheet有效行列数"""
    max_row = ws.max_row or 0
    max_col = ws.max_column or 0
    # 统计非空行数
    non_empty_rows = 0
    for row in ws.iter_rows():
        if any(cell.value is not None for cell in row):
            non_empty_rows += 1
    return {
        "max_row": max_row,
        "max_col": max_col,
        "non_empty_rows": non_empty_rows
    }


def analyze_workbook(path):
    """读取全部sheet并提取结构"""
    print(f"正在读取: {path}")
    wb = openpyxl.load_workbook(path, data_only=False)  # data_only=False保留公式
    
    sheets_info = []
    total_formulas = 0
    
    for idx, sheet_name in enumerate(wb.sheetnames):
        ws = wb[sheet_name]
        dims = get_sheet_dimensions(ws)
        formula_info = count_formulas(ws)
        total_formulas += formula_info["total"]
        
        # 找到真正的列头行
        header_row_num, columns, header_candidates = find_header_row(ws, max_scan=10)
        
        sheet_info = {
            "index": idx,
            "sheet_name": sheet_name,
            "max_row": dims["max_row"],
            "max_column": dims["max_col"],
            "non_empty_rows": dims["non_empty_rows"],
            "header_row": header_row_num,
            "column_names": columns,
            "column_count": len(columns),
            "formula_total": formula_info["total"],
            "formula_header_ref": formula_info["header_ref"],
            "formula_business": formula_info["business"],
            "sample_business_formulas": formula_info["business_formulas"][:10]
        }
        sheets_info.append(sheet_info)
        print(f"  [{idx}] {sheet_name}: {dims['non_empty_rows']}行 x {dims['max_col']}列, "
              f"总{formula_info['total']}公式(表头引用{formula_info['header_ref']}+业务{formula_info['business']})")
    
    return {
        "file": str(path),
        "sheet_count": len(wb.sheetnames),
        "total_formulas": total_formulas,
        "sheets": sheets_info
    }


def main():
    if not XLSX_PATH.exists():
        print(f"ERROR: 文件不存在: {XLSX_PATH}")
        return
    
    result = analyze_workbook(XLSX_PATH)
    
    # 提取关键确认信息
    k10_1_total = None
    k10_1_business = None
    k10_2_total = None
    k10_2_business = None
    for s in result["sheets"]:
        name = s["sheet_name"]
        if "K10-1" in name or "审定" in name:
            k10_1_total = s["formula_total"]
            k10_1_business = s["formula_business"]
        elif "K10-2" in name or "明细" in name:
            k10_2_total = s["formula_total"]
            k10_2_business = s["formula_business"]
    
    # 汇总验证
    # 注意：任务期望值69/11是初步估算
    # 实际openpyxl实读：K10-1总71公式(7表头+64业务)，K10-2总27公式(7表头+20业务)
    # K10-1 期望69≈总71-2(可能某些公式被认定为非业务)，以实读为权威
    # K10-2 期望11：可能只统计了合计行公式(SUM)，实际每数据行也有审定=未审+调整公式
    confirmation = {
        "K10-1_审定表": {
            "total_formulas": k10_1_total,
            "header_ref_formulas": k10_1_total - k10_1_business if k10_1_total and k10_1_business else None,
            "business_formulas": k10_1_business,
            "task_expected": 69,
            "actual_vs_expected": f"总{k10_1_total}=表头7+业务{k10_1_business}; 期望69介于总71和业务64之间",
            "note": "实际公式数以openpyxl实读为准，期望值69为初步估算"
        },
        "K10-2_明细表": {
            "total_formulas": k10_2_total,
            "header_ref_formulas": k10_2_total - k10_2_business if k10_2_total and k10_2_business else None,
            "business_formulas": k10_2_business,
            "task_expected": 11,
            "actual_vs_expected": f"总{k10_2_total}=表头7+业务{k10_2_business}; 期望11可能仅统计合计行",
            "note": "实际公式数以openpyxl实读为准，期望值11为初步估算"
        },
        "total_sheets": result["sheet_count"],
        "valid_sheets": result["sheet_count"] - 1,  # 排除GT_Custom
        "valid_sheet_names": [s["sheet_name"] for s in result["sheets"] if s["sheet_name"] != "GT_Custom"],
        "total_formulas": result["total_formulas"],
        "total_business_formulas": sum(s["formula_business"] for s in result["sheets"]),
        "双源输入确认": {
            "损益类科目": "6117其他收益",
            "取数规则": "发生额（贷方发生-借方发生），从tb_ledger取",
            "关键sheet": "审定表K10-1(64业务公式)+政府补助核对K10-4(54业务公式)",
            "10有效sheet": True,
            "公式驱动核心": "审定=未审+AJE+RJE; 发生额审定数=贷方-借方; 补助合计=直接+递延"
        }
    }
    
    output = {
        "task": "0.1 openpyxl脚本读取K10其他收益.xlsx全部10 sheet",
        "source": str(XLSX_PATH),
        "confirmation": confirmation,
        "sheet_details": result["sheets"]
    }
    
    # 写出JSON
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n=== 确认结果 ===")
    print(f"总sheet数: {result['sheet_count']} (有效10 + GT_Custom 1)")
    print(f"总公式数: {result['total_formulas']}")
    print(f"K10-1 审定表: 总{k10_1_total}公式 = 表头引用{k10_1_total - k10_1_business} + 业务{k10_1_business} (任务期望69)")
    print(f"K10-2 明细表: 总{k10_2_total}公式 = 表头引用{k10_2_total - k10_2_business} + 业务{k10_2_business} (任务期望11)")
    print(f"\n产出文件: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
