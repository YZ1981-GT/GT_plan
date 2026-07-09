"""
analyze_i6_structure.py
=======================
读取 I6 研发费用.xlsx 全部 11 sheet，提取结构信息并输出 JSON。

Phase 0 双源输入验证 - 任务 0.1

提取：sheet名 / 列头 / 行数 / 公式单元格 / 合并区域 / 数据类型
产出：.kiro/specs/i6-research-development-expense/i6_structure_summary.json

关键验证点：
- 确认 11 个有效 sheet（Glossary 定义）
- 确认损益类取数规则：6602 研发费用（借方科目），取发生额非余额
- 确认月度 12 列横向宽表结构（明细表 I6-2，65 列）
- 确认审定表 I6-1 使用"净发生额=借方-贷方"公式（非期末余额）
- 公式总数约 120+

科目特殊性：
- 6602 研发费用是**损益类/借方科目**
- TB 取数来源：tb_ledger 发生额汇总（非 tb_balance 期末余额）
- 净发生额 = 借方发生 - 贷方发生（借方=费用增加，贷方=费用冲回/结转）
- 底稿模板库中编号为 I7（底稿内部索引），xlsx 文件编号为 I6

用法：python backend/scripts/analyze_i6_structure.py
"""

import json
import os
import sys
from pathlib import Path
from collections import Counter

import openpyxl
from openpyxl.utils import get_column_letter


# ---------- 配置 ----------

_CANDIDATES = [
    Path(
        r"基础数据/致同通用审计程序及底稿模板（2025年修订）"
        r"/1.致同审计程序及底稿模板（2025年）"
        r"/4.风险应对-实质性程序（D-N）/I 无形资产循环/I6 研发费用.xlsx"
    ),
    Path(r"backend/wp_templates/I/I6 研发费用.xlsx"),
]

OUTPUT_FILE = Path(".kiro/specs/i6-research-development-expense/i6_structure_summary.json")

# Glossary 中描述的 11 个有效 sheet（名称关键词→预期特征）
# 注：底稿模板库中编号为 I7，xlsx 文件实际可能用 I6 或 I7
EXPECTED_SHEETS = {
    "Tab_Index": {"keyword": "目录", "expected_cols_approx": 5},
    "Procedure_Table_I6A": {"keyword": "I6A", "alt_keyword": "I7A", "expected_cols_approx": 13},
    "Adjudication_I6_1": {"keyword": "I6-1", "alt_keyword": "I7-1", "expected_cols_approx": 11},
    "Detail_I6_2": {"keyword": "I6-2", "alt_keyword": "I7-2", "expected_cols_approx": 65},
    "Adjustment_I6_3": {"keyword": "I6-3", "alt_keyword": "I7-3", "expected_cols_approx": 13},
    "Targeted_Check_I6_4": {"keyword": "I6-4", "alt_keyword": "I7-4", "expected_cols_approx": 12},
    "Cutoff_Forward_I6_5": {"keyword": "I6-5", "alt_keyword": "I7-5", "expected_cols_approx": 10},
    "Cutoff_Backward_I6_6": {"keyword": "I6-6", "alt_keyword": "I7-6", "expected_cols_approx": 10},
    "Disclosure_Listed": {"keyword": "上市", "expected_cols_approx": 7},
    "Disclosure_SOE": {"keyword": "国有", "alt_keyword": "国企", "expected_cols_approx": 6},
}


def find_source_file() -> Path:
    """按候选列表查找第一个存在的 xlsx 文件。"""
    project_root = Path(os.getcwd())
    for candidate in _CANDIDATES:
        if candidate.exists():
            return candidate
        abs_path = project_root / candidate
        if abs_path.exists():
            return abs_path
    print("ERROR: 找不到 I6 研发费用.xlsx，尝试过：")
    for c in _CANDIDATES:
        print(f"  - {c}")
        print(f"  - {project_root / c}")
    sys.exit(1)


def extract_headers(ws, max_scan_rows: int = 8) -> dict:
    """从前几行提取列头信息，返回所有可能的列头行。"""
    header_rows = {}
    for row_idx in range(1, min(max_scan_rows + 1, ws.max_row + 1)):
        headers = []
        for col_idx in range(1, ws.max_column + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            val = cell.value
            if val is not None:
                headers.append(str(val).strip())
            else:
                headers.append("")
        non_empty = [h for h in headers if h]
        if len(non_empty) >= 2:
            header_rows[f"row_{row_idx}"] = non_empty
    return header_rows


def extract_primary_headers(ws, max_scan_rows: int = 8) -> list[str]:
    """提取最可能是主列头的一行（非空数最多的行）。"""
    best_row = []
    best_count = 0
    for row_idx in range(1, min(max_scan_rows + 1, ws.max_row + 1)):
        headers = []
        for col_idx in range(1, ws.max_column + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            val = cell.value
            if val is not None:
                headers.append(str(val).strip())
            else:
                headers.append("")
        non_empty = sum(1 for h in headers if h)
        if non_empty > best_count:
            best_count = non_empty
            best_row = [h for h in headers if h]
    return best_row


def extract_formulas(ws) -> dict:
    """提取公式单元格信息。"""
    formulas = []
    formula_count = 0
    formula_by_col = Counter()
    formula_patterns = Counter()
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=ws.max_column):
        for cell in row:
            if cell.value and isinstance(cell.value, str) and cell.value.startswith("="):
                formula_count += 1
                col_letter = get_column_letter(cell.column)
                formula_by_col[col_letter] += 1
                if len(formulas) < 20:  # 保留前 20 个样例
                    formulas.append({
                        "cell": cell.coordinate,
                        "formula": cell.value,
                    })
                # 抽象公式模式（数字替换为 N）
                import re
                pattern = re.sub(r'\d+', 'N', cell.value)
                formula_patterns[pattern] += 1
    return {
        "count": formula_count,
        "samples": formulas,
        "by_column": dict(formula_by_col.most_common(15)),
        "patterns": dict(formula_patterns.most_common(20)),
    }


def extract_merged_areas(ws) -> list[str]:
    """提取合并单元格区域。"""
    return [str(r) for r in ws.merged_cells.ranges]


def extract_data_types(ws) -> dict:
    """统计各列数据类型分布（采样前 30 行数据区）。"""
    type_summary = {}
    data_start_row = min(6, ws.max_row)  # 跳过列头区
    sample_end_row = min(data_start_row + 30, ws.max_row)

    for col_idx in range(1, ws.max_column + 1):
        col_letter = get_column_letter(col_idx)
        types = Counter()
        for row_idx in range(data_start_row, sample_end_row + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            val = cell.value
            if val is None:
                types["null"] += 1
            elif isinstance(val, str):
                if val.startswith("="):
                    types["formula"] += 1
                else:
                    types["string"] += 1
            elif isinstance(val, (int, float)):
                types["number"] += 1
            elif hasattr(val, "strftime"):
                types["date"] += 1
            else:
                types["other"] += 1

        non_null_types = {k: v for k, v in types.items() if k != "null" and v > 0}
        if non_null_types:
            dominant_type = max(non_null_types, key=non_null_types.get)
            type_summary[col_letter] = dominant_type

    return type_summary


def extract_named_ranges(wb) -> list[dict]:
    """提取工作簿命名区域。"""
    named_ranges = []
    try:
        for name, defn in wb.defined_names.items():
            named_ranges.append({
                "name": name,
                "value": str(defn.attr_text) if hasattr(defn, "attr_text") else str(defn.value),
            })
    except (AttributeError, TypeError):
        try:
            for dn in wb.defined_names.definedName:
                named_ranges.append({
                    "name": dn.name,
                    "value": dn.attr_text,
                })
        except (AttributeError, TypeError):
            pass
    return named_ranges


def detect_monthly_columns(ws) -> dict:
    """
    检测月度 12 列横向结构。
    在前 8 行中寻找包含 "1月"~"12月" 或 "一月"~"十二月" 或 数字 1~12 的列头行。
    """
    import re
    month_keywords = [f"{i}月" for i in range(1, 13)]
    month_nums = [str(i) for i in range(1, 13)]

    for row_idx in range(1, min(9, ws.max_row + 1)):
        row_values = []
        for col_idx in range(1, ws.max_column + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            val = str(cell.value).strip() if cell.value else ""
            row_values.append(val)

        # 检查是否包含月度列头
        month_matches = 0
        month_cols = {}
        for col_idx, val in enumerate(row_values, 1):
            for m_kw in month_keywords:
                if m_kw in val:
                    month_matches += 1
                    month_cols[m_kw] = get_column_letter(col_idx)
                    break

        if month_matches >= 10:  # 至少找到 10 个月份列
            return {
                "detected": True,
                "header_row": row_idx,
                "month_count": month_matches,
                "month_columns": month_cols,
                "structure": "月度12列横向宽表",
            }

    return {"detected": False}


def detect_income_statement_formulas(ws) -> dict:
    """
    检测损益类取数特征：
    - 净发生额 = 借方发生 - 贷方发生（非期末余额）
    - 查找"借方"/"贷方"/"发生"/"净发生"等关键词
    """
    income_indicators = {
        "has_debit_credit_headers": False,
        "has_net_occurrence": False,
        "has_occurrence_formula": False,
        "debit_credit_formula_samples": [],
        "key_headers_found": [],
    }

    # 扫描前 10 行的列头
    for row_idx in range(1, min(11, ws.max_row + 1)):
        for col_idx in range(1, ws.max_column + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            val = str(cell.value).strip() if cell.value else ""
            if "借方" in val or "贷方" in val:
                income_indicators["has_debit_credit_headers"] = True
                income_indicators["key_headers_found"].append(f"{cell.coordinate}: {val}")
            if "发生" in val:
                income_indicators["has_net_occurrence"] = True
                income_indicators["key_headers_found"].append(f"{cell.coordinate}: {val}")
            if "净" in val and "发生" in val:
                income_indicators["key_headers_found"].append(f"{cell.coordinate}: {val}")

    # 扫描公式中是否有 借-贷 模式
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=ws.max_column):
        for cell in row:
            if cell.value and isinstance(cell.value, str) and cell.value.startswith("="):
                formula = cell.value.lower()
                # 检测 A-B 类型的差额公式（损益类净发生额特征）
                if len(income_indicators["debit_credit_formula_samples"]) < 5:
                    # 简单减法公式 =X-Y
                    import re
                    if re.match(r'^=[A-Z]+\d+-[A-Z]+\d+$', cell.value):
                        income_indicators["has_occurrence_formula"] = True
                        income_indicators["debit_credit_formula_samples"].append({
                            "cell": cell.coordinate,
                            "formula": cell.value,
                        })

    return income_indicators


def validate_against_glossary(sheets: list[dict]) -> dict:
    """将实际 sheet 结构与 Glossary 预期进行对照验证。"""
    validation = {
        "total_sheets": len(sheets),
        "expected_effective_sheets": 11,
        "match": False,
        "matched_glossary_entries": [],
        "unmatched_glossary_entries": [],
        "sheet_mapping": {},
        "extra_sheets": [],
    }

    sheet_names = [s["name"] for s in sheets]

    for glossary_key, expected in EXPECTED_SHEETS.items():
        keyword = expected["keyword"]
        alt_keyword = expected.get("alt_keyword", "")
        matched_sheet = None
        for sname in sheet_names:
            if keyword in sname or (alt_keyword and alt_keyword in sname):
                matched_sheet = sname
                break

        if matched_sheet:
            validation["matched_glossary_entries"].append(glossary_key)
            validation["sheet_mapping"][glossary_key] = matched_sheet
        else:
            validation["unmatched_glossary_entries"].append(glossary_key)

    # 标记额外的 sheet（如 GT_Custom 等）
    matched_names = set(validation["sheet_mapping"].values())
    for sname in sheet_names:
        if sname not in matched_names:
            validation["extra_sheets"].append(sname)

    # 11 个有效 sheet = 匹配到的 Glossary 条目数
    validation["match"] = len(validation["matched_glossary_entries"]) >= 10

    return validation


def main():
    # 切换到项目根目录
    project_root = Path(__file__).resolve().parent.parent.parent
    os.chdir(project_root)

    source_file = find_source_file()
    print(f"📂 读取文件: {source_file}")
    print(f"   文件大小: {source_file.stat().st_size / 1024:.1f} KB")

    # data_only=False 以读取公式而非计算结果
    wb = openpyxl.load_workbook(str(source_file), data_only=False, read_only=False)

    # 提取命名区域
    named_ranges = extract_named_ranges(wb)

    result = {
        "source_file": str(source_file),
        "file_size_kb": round(source_file.stat().st_size / 1024, 1),
        "科目": "6602 研发费用",
        "科目方向": "借方/损益类",
        "取数规则": "损益类取发生额（非期末余额）！从 tb_ledger 汇总，净发生额=借方发生-贷方发生",
        "sheet_count": len(wb.sheetnames),
        "sheet_names": wb.sheetnames,
        "named_ranges": named_ranges,
        "sheets": [],
        "月度12列验证": None,
        "损益类取数验证": None,
        "validation": None,
        "summary": {},
    }

    print(f"\n共 {len(wb.sheetnames)} 个 sheet:")
    print("-" * 70)

    total_formulas = 0
    total_merged = 0
    monthly_detection = None
    income_stmt_detection = None

    for idx, name in enumerate(wb.sheetnames, 1):
        ws = wb[name]
        print(f"  [{idx:2d}] {name}")
        print(f"       尺寸: {ws.max_row}行 × {ws.max_column}列")

        # 提取各项结构信息
        all_headers = extract_headers(ws)
        primary_headers = extract_primary_headers(ws)
        formula_info = extract_formulas(ws)
        merged_areas = extract_merged_areas(ws)
        data_types = extract_data_types(ws)

        total_formulas += formula_info["count"]
        total_merged += len(merged_areas)

        print(f"       列头: {len(primary_headers)}列 | 公式: {formula_info['count']}个 | 合并: {len(merged_areas)}个")

        sheet_info = {
            "index": idx,
            "name": name,
            "rows": ws.max_row,
            "cols": ws.max_column,
            "dimensions": f"{ws.max_row}行 × {ws.max_column}列",
            "primary_headers": primary_headers,
            "all_header_rows": all_headers,
            "formula_count": formula_info["count"],
            "formula_samples": formula_info["samples"],
            "formula_by_column": formula_info["by_column"],
            "formula_patterns": formula_info["patterns"],
            "merged_areas": merged_areas,
            "merged_area_count": len(merged_areas),
            "data_types": data_types,
        }

        # 对明细表检测月度 12 列结构
        if "明细" in name or "I6-2" in name or "I7-2" in name:
            monthly = detect_monthly_columns(ws)
            sheet_info["monthly_structure"] = monthly
            if monthly["detected"]:
                monthly_detection = monthly
                print(f"       ✅ 检测到月度12列横向结构 (行{monthly['header_row']})")

        # 对审定表检测损益类公式特征
        if "审定" in name or "I6-1" in name or "I7-1" in name:
            income_stmt = detect_income_statement_formulas(ws)
            sheet_info["income_statement_indicators"] = income_stmt
            income_stmt_detection = income_stmt
            if income_stmt["has_debit_credit_headers"]:
                print(f"       ✅ 检测到损益类借/贷方发生额列头")

        result["sheets"].append(sheet_info)

    # 月度 12 列验证结论
    result["月度12列验证"] = monthly_detection or {"detected": False, "note": "未在明细表中检测到12列月度结构"}

    # 损益类取数验证结论
    result["损益类取数验证"] = income_stmt_detection or {"note": "未检测到审定表损益类特征"}

    # Glossary 验证
    print("\n" + "=" * 70)
    print("📋 Glossary 对照验证:")
    validation = validate_against_glossary(result["sheets"])
    result["validation"] = validation

    if validation["match"]:
        print(f"  ✅ 有效 sheet 匹配: {len(validation['matched_glossary_entries'])}/{len(EXPECTED_SHEETS)}")
    else:
        print(f"  ⚠️ 有效 sheet 匹配不足: {len(validation['matched_glossary_entries'])}/{len(EXPECTED_SHEETS)}")

    print(f"  已匹配 Glossary 条目: {len(validation['matched_glossary_entries'])}/{len(EXPECTED_SHEETS)}")
    if validation["unmatched_glossary_entries"]:
        print(f"  ❌ 未匹配条目: {validation['unmatched_glossary_entries']}")
    if validation["extra_sheets"]:
        print(f"  📌 额外 sheet: {validation['extra_sheets']}")

    # 汇总
    result["summary"] = {
        "total_sheets": len(wb.sheetnames),
        "effective_sheets": len(validation["matched_glossary_entries"]),
        "total_formulas": total_formulas,
        "total_merged_areas": total_merged,
        "total_rows": sum(s["rows"] for s in result["sheets"]),
        "total_cols_max": max(s["cols"] for s in result["sheets"]),
        "avg_rows_per_sheet": round(sum(s["rows"] for s in result["sheets"]) / len(result["sheets"]), 1),
        "named_range_count": len(named_ranges),
        "income_statement_type": True,
        "data_source": "tb_ledger（发生额汇总，非 tb_balance 期末余额）",
        "monthly_12_column": monthly_detection["detected"] if monthly_detection else False,
    }

    # 输出
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 产出文件: {OUTPUT_FILE}")
    print(f"   sheet 数量: {result['sheet_count']}")
    print(f"   公式总数: {total_formulas}")
    print(f"   合并区域总数: {total_merged}")
    print(f"   数据行总数: {result['summary']['total_rows']}")
    print(f"   最大列数: {result['summary']['total_cols_max']}")
    print(f"   命名区域: {len(named_ranges)}")

    # 特殊关注点
    print("\n📌 I6 关键特征检查:")
    print(f"   科目类型: 损益类（6602 研发费用）")
    print(f"   取数规则: 取发生额非余额（借方=费用增加，贷方=费用冲回）")
    print(f"   月度12列: {'✅ 已确认' if result['summary']['monthly_12_column'] else '⚠️ 未检测到'}")

    for sheet in result["sheets"]:
        if sheet["cols"] >= 50:
            print(f"   ⚡ 极宽表: {sheet['name']} ({sheet['cols']}列)")
        if sheet["formula_count"] >= 20:
            print(f"   📐 公式密集: {sheet['name']} ({sheet['formula_count']}公式)")

    # I6↔I2 联动验证提示
    print("\n📌 I6↔I2 双向联动确认:")
    print("   VR-I6-01: 费用化(I6) + 资本化(I2) = 研发总额")
    print("   EventBus: research:expense-updated / development:capitalized-updated")
    print("   cross_wp_references: 双向引用")

    wb.close()
    return result


if __name__ == "__main__":
    main()
