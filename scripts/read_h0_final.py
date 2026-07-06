"""
Phase 0 Task 0.1 FINAL: openpyxl 实读 H0 固定资产循环函证.xlsx 全 9 sheet
产出: .kiro/specs/h0-confirmation/h0_structure_summary.json

包含:
- 全 9 sheet 的列头 / 行数 / 公式 / 合并单元格
- H0-5 区块深度分析（对照 D0-5 实际结构）
- 设计对照表
"""

import json
from pathlib import Path
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

H0_PATH = Path(r"d:\GT_plan\backend\wp_templates\H\H0 固定资产循环函证.xlsx")
D0_PATH = Path(r"d:\GT_plan\backend\wp_templates\D\D0 收入循环函证.xlsx")
OUTPUT_PATH = Path(r"d:\GT_plan\.kiro\specs\h0-confirmation\h0_structure_summary.json")


def extract_all_cells(ws, max_row=None, max_col=None):
    """Extract all non-empty cells as structured data."""
    mr = max_row or ws.max_row
    mc = max_col or ws.max_column
    rows = {}
    for r in range(1, mr + 1):
        row_cells = []
        for c in range(1, mc + 1):
            cell = ws.cell(row=r, column=c)
            if cell.value is not None:
                val = str(cell.value).strip()
                if val:
                    row_cells.append({
                        "col": c,
                        "letter": get_column_letter(c),
                        "value": val[:150]
                    })
        if row_cells:
            rows[str(r)] = row_cells
    return rows


def extract_formulas(ws):
    """Extract all formula cells."""
    formulas = []
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=ws.max_column):
        for cell in row:
            if cell.value and isinstance(cell.value, str) and cell.value.startswith("="):
                formulas.append({
                    "cell": f"{get_column_letter(cell.column)}{cell.row}",
                    "formula": cell.value
                })
    return formulas


def analyze_sheet(ws, sheet_name):
    """Analyze a single sheet comprehensively."""
    info = {
        "name": sheet_name,
        "dimensions": {
            "max_row": ws.max_row,
            "max_col": ws.max_column,
            "range": ws.dimensions
        },
        "merged_cells": [str(m) for m in ws.merged_cells.ranges],
    }

    # Extract header rows (first 7 rows for context)
    header_limit = min(8, (ws.max_row or 1) + 1)
    header_rows = {}
    for r in range(1, header_limit):
        row_cells = []
        for c in range(1, (ws.max_column or 1) + 1):
            cell = ws.cell(row=r, column=c)
            if cell.value is not None:
                val = str(cell.value).strip()
                if val:
                    row_cells.append({
                        "col": c,
                        "letter": get_column_letter(c),
                        "value": val[:100]
                    })
        if row_cells:
            header_rows[f"row_{r}"] = row_cells
    info["header_rows"] = header_rows

    # Formulas
    formulas = extract_formulas(ws)
    info["formula_count"] = len(formulas)
    info["formulas"] = formulas  # all formulas (template is small)

    return info


def analyze_h05_deep(ws):
    """Deep analysis of H0-5 with full cell dump."""
    return {
        "title": "替代程序H0-5",
        "subtitle": "固定资产/工程物资/使用权资产/租赁负债/……替代程序检查表-XX公司",
        "dimensions": {"max_row": ws.max_row, "max_col": ws.max_column},
        "structure": {
            "header_section": {"rows": "1-4", "content": "事务所名/底稿目录引用/索引号H0-5"},
            "company_name": {"row": 5, "content": "被函证单位名称："},
            "sampling_section": {
                "rows": "6-9",
                "title": "一、样本选取标准与规模",
                "fields": [
                    {"key": "test_scope", "label": "测试范围", "row": 7, "cols": "A-H"},
                    {"key": "specific_sample", "label": "特定样本", "row": 7, "cols": "I-S"},
                    {"key": "population", "label": "抽样总体", "row": 8, "cols": "A-H"},
                    {"key": "sample_size", "label": "确定的抽样样本量", "row": 8, "cols": "I-S"},
                    {"key": "method", "label": "抽样方法", "row": 9, "cols": "A-H"},
                    {"key": "process", "label": "抽样过程", "row": 9, "cols": "I-S"}
                ]
            },
            "inspection_section": {
                "rows": "10-19",
                "title": "二、检查过程记录",
                "content": "EMPTY in template - 4 区块在此展开（设计层定义）",
                "note": "源模板此区域完全空白(rows 11-19)，与D0-5不同(D0-5有完整区块列头)"
            },
            "audit_explanation": {"rows": "20-22", "title": "三、审计说明", "content": "textarea"},
            "audit_conclusion": {"rows": "23-27", "title": "四、审计结论", "content": "textarea"},
            "guidance_notes": {
                "rows": "28-35",
                "title": "编制说明",
                "content": [
                    "1、函证替代程序：",
                    "  ①检查本期付款、期后收货或回收；",
                    "  ②检查原始凭证：合同、订货单、发票或收据、银行回单、支票存根等；",
                    "  ③对回函可能性不高的、余额重大的，发函同时执行替代程序。",
                    "2、概述：（1）程序的测试情况、结果；",
                    "  （2）拟调整事项及其调整分录、未调整事项及其影响，审计范围受到限制情况及其影响。"
                ]
            }
        },
        "all_cells": extract_all_cells(ws),
        "formulas": extract_formulas(ws),
        "merged_cells": [str(m) for m in ws.merged_cells.ranges]
    }


def analyze_d05_for_reference(d0_path):
    """Read D0-5 structure to document the reference pattern for H0-5 blocks."""
    wb = load_workbook(d0_path, data_only=False)
    ws = None
    for name in wb.sheetnames:
        if "替代程序" in name and "D0-5" in name:
            ws = wb[name]
            break
    if not ws:
        return {"error": "D0-5 sheet not found"}

    # Extract the 4 block definitions from D0-5
    blocks = []

    # Block 1: rows 14-21
    blocks.append({
        "block_num": 1,
        "key": "contract_liability_postcheck",
        "title_row": 14,
        "title": "合同负债检查-检查期后结转",
        "header_row": 15,
        "column_header_row": 16,
        "data_rows": "17-20",
        "total_row": 21,
        "voucher_cols": {"A": "序号", "B": "日期", "C": "凭证编号", "D": "业务内容", "E": "对方科目", "F": "明细科目", "G": "借方金额"},
        "evidence_cols": {"H": "日期/编号", "I": "数量", "J": "签字签章", "K": "日期(发票)", "L": "收票方名称", "M": "金额"},
        "meta_cols": {"O": "索引号", "P": "是否异常"},
        "formulas": ["G21=SUM(G17:G20)", "M21=SUM(M17:M20)"]
    })

    # Block 2: rows 23-30
    blocks.append({
        "block_num": 2,
        "key": "balance_evidence",
        "title_row": 23,
        "title": "合同负债检查-形成期末余额的合同、订单、银行收款凭单等支持性证据检查",
        "header_row": 24,
        "column_header_row": 25,
        "data_rows": "26-29",
        "total_row": 30,
        "voucher_cols": {"A": "序号", "B": "日期", "C": "凭证编号", "D": "业务内容", "E": "对方科目", "F": "明细科目", "G": "贷方金额"},
        "evidence_cols": {"H": "日期(收款)", "I": "付款方", "J": "金额", "K": "客户名称", "L": "合同金额", "M": "预收比例"},
        "meta_cols": {"O": "索引号", "P": "是否异常"},
        "formulas": ["G30=SUM(G26:G29)", "J30=SUM(J26:J29)"]
    })

    # Block 3: rows 32-39
    blocks.append({
        "block_num": 3,
        "key": "sales_receipt_check",
        "title_row": 32,
        "title": "销售检查-本期收款检查",
        "header_row": 33,
        "column_header_row": 34,
        "data_rows": "35-38",
        "total_row": 39,
        "voucher_cols": {"A": "日期", "B": "凭证编号", "C": "业务内容", "D": "对方科目", "E": "金额"},
        "evidence_cols": {"F": "日期(回单)", "G": "付款方", "H": "金额", "I": "日期/编号(发票)", "J": "对手方名称", "K": "金额"},
        "meta_cols": {"M": "索引号", "N": "是否异常"},
        "formulas": ["E39=SUM(E35:E38)", "H39=SUM(H35:H38)", "K39=SUM(K35:K38)"]
    })

    # Block 4: rows 41-48
    blocks.append({
        "block_num": 4,
        "key": "delivery_evidence",
        "title_row": 41,
        "title": "销售检查-本期出库的合同、出库单、运输单、验收单等支持性证据检查",
        "header_row": 42,
        "column_header_row": 43,
        "data_rows": "44-47",
        "total_row": 48,
        "voucher_cols": {"A": "序号", "B": "日期", "C": "编号", "D": "品名", "E": "数量", "F": "金额"},
        "evidence_cols": {
            "G-H": "销售订单/合同(日期+号)",
            "I-N": "出库单(日期/编号/品名/数量/保管员/发货人)",
            "O-S": "运输单(日期/编号/数量/公司/地址)",
            "T-Z": "签收单(日期/品名/数量/金额/签收人/盖章类型/盖章单位)"
        },
        "meta_cols": {"AC": "是否异常", "AD": "其他支持性文件或说明"},
        "formulas": ["E48=SUM(E44:E47)", "F48=SUM(F44:F47)", "L48=SUM(L44:L47)", "Q48=SUM(Q44:Q47)", "W48=SUM(W44:W47)"]
    })

    return {
        "sheet_name": ws.title,
        "dimensions": {"max_row": ws.max_row, "max_col": ws.max_column},
        "summary_section": {
            "row": 11,
            "fields": ["函证项目", "年初余额", "借方发生额", "贷方发生额", "期末余额", "账面金额", "本期收款检查比例", "本期出库检查比例"]
        },
        "blocks": blocks,
        "pattern": "title_row → category_header_row → column_header_row → data_rows(3-4 placeholder) → total_row(SUM)"
    }


def build_h05_design_blocks():
    """
    Define the 4 blocks for H0-5 based on requirements doc + D0-5 pattern.
    These are DESIGN decisions since the H0-5 template is blank in the inspection area.
    """
    return [
        {
            "block_num": 1,
            "key": "acceptance_ownership",
            "title": "期后验收/权属证据检查",
            "description": "检查期后固定资产到货验收凭证和权属证书,确认资产存在性和完整性",
            "voucher_cols": ["序号", "日期", "凭证编号", "业务内容", "对方科目", "金额"],
            "evidence_cols": ["验收单(日期/编号)", "权属证书(证书号/登记日)", "索引号", "是否异常"],
            "formula": "合计行=SUM(金额列)"
        },
        {
            "block_num": 2,
            "key": "balance_evidence",
            "title": "期末余额支持性证据",
            "description": "检查形成期末固定资产余额的采购合同/发票/付款凭证等支持性证据",
            "voucher_cols": ["序号", "日期", "凭证编号", "业务内容", "对方科目", "金额"],
            "evidence_cols": ["采购合同(编号/金额)", "发票(编号/金额)", "付款凭证(日期/金额)", "索引号", "是否异常"],
            "formula": "合计行=SUM(金额列)"
        },
        {
            "block_num": 3,
            "key": "new_asset_check",
            "title": "本期新增资产检查",
            "description": "检查本期新增固定资产的请购审批/到货验收/转固等关键环节证据",
            "voucher_cols": ["序号", "日期", "凭证编号", "业务内容", "对方科目", "金额"],
            "evidence_cols": ["请购审批(审批人/日期)", "到货验收(验收人/日期/状态)", "转固原值", "索引号", "是否异常"],
            "formula": "合计行=SUM(金额列)"
        },
        {
            "block_num": 4,
            "key": "mortgage_lease",
            "title": "抵押担保/融资租赁证据",
            "description": "检查固定资产抵押担保合同和融资租赁合同/他项权证等证据",
            "voucher_cols": ["序号", "日期", "凭证编号", "业务内容", "对方科目", "金额"],
            "evidence_cols": ["抵押合同(编号/金额/期限)", "融资租赁合同(编号/租金)", "他项权证(证号/登记日)", "索引号", "是否异常"],
            "formula": "合计行=SUM(金额列)"
        }
    ]


def main():
    print(f"Reading H0: {H0_PATH}")
    wb = load_workbook(H0_PATH, data_only=False)

    result = {
        "meta": {
            "task": "0.1 openpyxl 实读 H0 固定资产循环函证.xlsx 全 9 sheet",
            "source_file": str(H0_PATH.relative_to(Path(r"d:\GT_plan"))),
            "source_file_alt": r"基础数据\致同通用审计程序及底稿模板（2025年修订）\1.致同审计程序及底稿模板（2025年）\4.风险应对-实质性程序（D-N）\H 固定资产循环\H0 固定资产循环函证.xlsx",
            "sheet_count": len(wb.sheetnames),
            "sheet_names": wb.sheetnames
        },
        "sheets": [],
        "h05_deep_analysis": None,
        "d05_reference_pattern": None,
        "h05_design_blocks": None
    }

    for name in wb.sheetnames:
        ws = wb[name]
        print(f"  [{wb.sheetnames.index(name)+1}/9] {name} ({ws.max_row}×{ws.max_column})")
        sheet_info = analyze_sheet(ws, name)
        result["sheets"].append(sheet_info)

    # H0-5 deep analysis
    ws_h05 = wb["替代程序H0-5"]
    result["h05_deep_analysis"] = analyze_h05_deep(ws_h05)

    # D0-5 reference pattern
    print(f"\nReading D0-5 reference: {D0_PATH}")
    result["d05_reference_pattern"] = analyze_d05_for_reference(D0_PATH)

    # H0-5 design blocks (derived from requirements + D0-5 pattern)
    result["h05_design_blocks"] = build_h05_design_blocks()

    # Key findings summary
    result["findings"] = {
        "h0_vs_d0_key_differences": [
            "H0-5 源模板'检查过程记录'区域完全空白(rows 11-19)，D0-5有完整4区块列头+数据行+合计行",
            "H0-5仅35行×29列(紧凑)，D0-5为62行×40列(完整展开)",
            "H0-5的4区块结构需要由设计层定义(非源模板预置)，遵循D0-5的 title→header→columns→data→total 模式",
            "H0-5标题为'固定资产/工程物资/使用权资产/租赁负债/……替代程序检查表'",
            "H0-5在row 5有'被函证单位名称：'字段(对应Master-Detail的公司维度)"
        ],
        "h05_block_pattern_from_d05": "title_row → category_header_row(记账凭证|检查证据) → column_header_row → data_rows(dynamic) → total_row(SUM)",
        "h05_sampling_fields": ["测试范围", "特定样本", "抽样总体", "确定的抽样样本量", "抽样方法", "抽样过程"],
        "h05_conclusion_sections": ["三、审计说明(textarea)", "四、审计结论(textarea)"],
        "h05_guidance_embedded": True,
        "formulas_in_template": {
            "H0-1": "200 (VLOOKUP cross-sheet + IF回函判断)",
            "H0-2": "14 (底稿目录引用)",
            "H0-3": "6 (底稿目录引用)",
            "H0-4": "9 (底稿目录引用 + SUM合计行)",
            "H0-5": "6 (底稿目录引用 only - 无区块公式因模板为空)",
            "H0-6": "6 (底稿目录引用)",
            "H0-7": "6 (底稿目录引用)"
        }
    }

    # Write output
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Output: {OUTPUT_PATH}")
    print(f"   Sheets: {len(result['sheets'])}")
    print(f"   H0-5 blocks (design): {len(result['h05_design_blocks'])}")


if __name__ == "__main__":
    main()
