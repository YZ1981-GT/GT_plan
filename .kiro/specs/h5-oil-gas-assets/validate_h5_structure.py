"""
Validate h5_structure_summary.json against spec glossary expectations.
"""
import json
from pathlib import Path

OUTPUT_PATH = Path(__file__).parent / "h5_structure_summary.json"

# Spec expected structure from requirements.md glossary
SPEC_EXPECTED = {
    "底稿目录": {"rows": 25, "cols": 8, "glossary_id": "Tab_Index"},
    "油气资产实质性程序表H5A": {"rows": 35, "cols": 12, "glossary_id": "Procedure_Table_H5A"},
    "审定表H5-1": {"rows": 75, "cols": 10, "glossary_id": "Adjudication_H5_1"},
    "附注披露信息（上市公司）": {"rows": 38, "cols": 257, "glossary_id": "Disclosure_Listed"},
    "附注披露信息（国有企业）": {"rows": 24, "cols": 253, "glossary_id": "Disclosure_SOE"},
    "明细表H5-2": {"rows": 53, "cols": 54, "glossary_id": "Detail_H5_2"},
    "调整分录汇总H5-3": {"rows": 23, "cols": 10, "glossary_id": "Adjustment_H5_3"},
    "闲置检查表H5-4": {"rows": 36, "cols": 11, "glossary_id": "Idle_Check_H5_4"},
    "会计政策会计估计检查表H5-5": {"rows": 46, "cols": 16, "glossary_id": "Policy_Check_H5_5"},
    "分析表H5-6": {"rows": 26, "cols": 23, "glossary_id": "Analysis_H5_6"},
    "增加检查表H5-7": {"rows": 40, "cols": 24, "glossary_id": "Addition_Check_H5_7"},
    "减少检查表H5-8": {"rows": 41, "cols": 24, "glossary_id": "Disposal_Check_H5_8"},
    "监盘计划H5-9": {"rows": 62, "cols": 15, "glossary_id": "Stocktake_Plan_H5_9"},
    "盘点检查表H5-10": {"rows": 64, "cols": 14, "glossary_id": "Stocktake_Check_H5_10"},
    "监盘小结H5-11": {"rows": 96, "cols": 10, "glossary_id": "Stocktake_Summary_H5_11"},
    "折耗测算表（不含减值）H5-12": {"rows": 46, "cols": 28, "glossary_id": "Depletion_NoImpair_H5_12"},
    "折耗测算表（含减值）H5-12": {"rows": 50, "cols": 28, "glossary_id": "Depletion_WithImpair_H5_12"},
    "折耗分配分析表H5-13": {"rows": 27, "cols": 10, "glossary_id": "Depletion_Alloc_H5_13"},
    "减值测算表H5-14": {"rows": 34, "cols": 32, "glossary_id": "Impairment_H5_14"},
    "可收回金额测试表H5-15": {"rows": 64, "cols": 28, "glossary_id": "Recoverable_H5_15"},
    "权属检查表H5-16": {"rows": 91, "cols": 21, "glossary_id": "Title_Check_H5_16"},
    "关联交易检查表H5-17": {"rows": 102, "cols": 16, "glossary_id": "Related_Party_H5_17"},
    "经营租出油气资产检查表H5-18": {"rows": 96, "cols": 17, "glossary_id": "Operating_Lease_H5_18"},
    "融资租出油气资产检查表H5-19": {"rows": 125, "cols": 20, "glossary_id": "Finance_Lease_H5_19"},
}


def main():
    with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    print("=== H5 Structure Validation: actual xlsx vs spec glossary ===\n")

    # 1. Sheet count
    actual_count = data["total_sheets"]
    expected_count = 24
    count_ok = actual_count == expected_count
    print(f"Sheet count: actual={actual_count}, expected={expected_count} -> {'PASS' if count_ok else 'FAIL'}")

    # 2. Per-sheet validation
    print(f"\n{'Sheet Name':<40s} {'Rows':>8s} {'Cols':>8s} {'Status':>8s}")
    print("-" * 70)

    all_pass = True
    validation_results = []

    for sheet in data["sheets"]:
        name = sheet["sheet_name"]
        if name in SPEC_EXPECTED:
            exp = SPEC_EXPECTED[name]
            r_ok = sheet["row_count"] == exp["rows"]
            c_ok = sheet["column_count"] == exp["cols"]
            row_str = f"{sheet['row_count']}({'OK' if r_ok else 'exp:' + str(exp['rows'])})"
            col_str = f"{sheet['column_count']}({'OK' if c_ok else 'exp:' + str(exp['cols'])})"
            status = "PASS" if (r_ok and c_ok) else "DIFF"
            if not (r_ok and c_ok):
                all_pass = False
            validation_results.append({
                "sheet_name": name,
                "glossary_id": exp["glossary_id"],
                "actual_rows": sheet["row_count"],
                "expected_rows": exp["rows"],
                "rows_match": r_ok,
                "actual_cols": sheet["column_count"],
                "expected_cols": exp["cols"],
                "cols_match": c_ok,
                "formula_count": sheet["formula_count"],
                "merged_count": sheet["merged_count"],
            })
            print(f"  {name:<38s} {row_str:>8s} {col_str:>8s} {status:>8s}")
        else:
            print(f"  {name:<38s} {'???':>8s} {'???':>8s} {'NO_SPEC':>8s}")
            all_pass = False

    # 3. Formula count totals
    total_formulas = sum(s["formula_count"] for s in data["sheets"])
    print(f"\nTotal formulas across all sheets: {total_formulas}")
    print(f"Spec estimate: ~200+ formulas -> {'PASS' if total_formulas > 200 else 'CHECK'}")

    # 4. Overall result
    print(f"\n{'='*70}")
    print(f"Overall validation: {'ALL MATCH' if all_pass else 'SOME DIFFERENCES FOUND'}")
    print(f"{'='*70}")

    # 5. Update the JSON with validation results
    data["validation"]["per_sheet_validation"] = validation_results
    data["validation"]["all_sheets_match_spec"] = all_pass
    data["validation"]["total_formula_count"] = total_formulas

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\nUpdated validation results written to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
