#!/usr/bin/env python
"""K 循环公式预设修正幂等脚本。

修正 `prefill_formula_mapping.json` 中 K3~K13 的 9 个错位块 + 移除 K14~K18 的
5 个孤儿块 + 清 K6 的病态区间 + 纠正 K5 明细块的科目码。

**根因**：`prefill_formula_mapping.json` 的 K 块全部按「遗留审定表族」编号写入，
与平台真实的致同 2025 模板族（`backend/wp_templates/K/*.xlsx` + `RENDERER_DISPATCH`
+ `componentType` 三方一致）全面错位。

**实证**（`report_config` + `account_chart` + `tb_balance` + `trial_balance` 四表交叉）::

    wp_code | 预设 wp_name       | 预设 accounts | 真实循环  | 真值科目
    K3      | 财务费用审定表      | ['6603']      | 其他应付款 | 2241
    K4      | 研发费用审定表      | ['6604']      | 其他流动负债| 无（宁缺勿造）
    K5      | 税金及附加审定表    | ['6403']      | 预计负债   | 2801
    K5(明细)| 预计负债明细        | ['2241']+2701 | 预计负债   | 2801
    K6      | 持有待售...审定表   | ['1481','2331']| 持有待售  | 无
    K7      | 预付款项审定表      | ['1123']      | 递延收益   | 2401
    K10     | 营业外收入审定表    | ['6301']      | 其他收益   | 6117
    K11     | 营业外支出审定表    | ['6711']      | 资产减值损失| 6701
    K12     | 信用减值损失审定表  | ['6701']      | 营业外收入 | 6301
    K13     | 资产减值损失审定表  | ['6702']      | 营业外支出 | 6711
    K14~K18 | (5 个)              | 各异          | 平台无循环 | 孤儿

**操作**：
- `--dry-run`（默认）：只报告变更，不写盘
- `--check`：报告后以 exit code 指示（0=无需变更，1=有欠账）
- `--apply`：执行变更并写盘

**幂等性**：多次 `--apply` 的结果与一次相同（已修正的块不再触发变更）。

spec: .kiro/specs/k-cycle-four-table-extraction-and-disclosure-completion/
      Task 15 / Requirements 7.1~7.5 / Property 12, 13, 14, 15
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "prefill_formula_mapping.json"

# ─────────────────────────────────────────────────────────────────────────────
# 正确科目映射（report_config 实证，k_cycle_specs.py 单一真源）
# ─────────────────────────────────────────────────────────────────────────────

CORRECT_ACCOUNTS: dict[str, str | None] = {
    "K3": "2241",   # 其他应付款 BS-053/BS-075
    "K4": None,     # 其他流动负债 三表零命中
    "K5": "2801",   # 预计负债 BS-068/BS-094
    "K6": None,     # 持有待售 四行 formula 全 None
    "K7": "2401",   # 递延收益 BS-069/BS-095
    "K8": "6601",   # 销售费用 IS-004/IS-022
    "K9": "6602",   # 管理费用 IS-005/IS-023
    "K10": "6117",  # 其他收益 IS-010/IS-030
    "K11": "6701",  # 资产减值损失 IS-017/IS-038 (None→兜底)
    "K12": "6301",  # 营业外收入 IS-020/IS-041
    "K13": "6711",  # 营业外支出 IS-021/IS-043
}

CORRECT_WP_NAMES: dict[str, str] = {
    "K3": "其他应付款审定表",
    "K4": "其他流动负债审定表",
    "K5": "预计负债审定表",
    "K6": "持有待售资产和负债审定表",
    "K7": "递延收益审定表",
    "K8": "销售费用审定表",
    "K9": "管理费用审定表",
    "K10": "其他收益审定表",
    "K11": "资产减值损失审定表",
    "K12": "营业外收入审定表",
    "K13": "营业外支出审定表",
}

ORPHAN_WP_CODES = {"K14", "K15", "K16", "K17", "K18"}

# K5 明细块的错误科目：原写 2241（其他应付款）和公式里写 2701（长期应付款）
K5_DETAIL_WRONG_CODES = {"2241", "2701"}


def _build_correct_cells(wp_code: str, acct: str | None) -> list[dict]:
    """为主审定表块生成正确的 cells（只含基础公式：TB + ADJ + PREV）。"""
    if acct is None:
        return []  # 宁缺勿造：不含 TB() 公式
    is_pl = acct.startswith("6")
    period = "本期发生额" if is_pl else "期末余额"
    period_begin = "本期发生额" if is_pl else "期初余额"
    # 损益类只有本期发生额口径
    cells = [
        {"cell_ref": "期初余额", "formula": f"=TB('{acct}','{period_begin}')",
         "label": f"从试算表取{CORRECT_WP_NAMES[wp_code][:4]}{period_begin}",
         "description": f"科目由报表行映射解析（k_cycle_specs 声明真源），兜底 {acct}"},
        {"cell_ref": "未审数", "formula": f"=TB('{acct}','{period}')",
         "label": f"从试算表取{CORRECT_WP_NAMES[wp_code][:4]}{period}（未审）",
         "description": f"四表取数权威口径 = trial_balance"},
        {"cell_ref": "AJE调整", "formula": f"=ADJ('{acct}','aje_net')",
         "label": f"{CORRECT_WP_NAMES[wp_code][:4]}审计调整分录净额",
         "description": ""},
        {"cell_ref": "RJE调整", "formula": f"=ADJ('{acct}','rje_net')",
         "label": f"{CORRECT_WP_NAMES[wp_code][:4]}重分类调整分录净额",
         "description": ""},
        {"cell_ref": "上年审定数", "formula": f"=PREV('{wp_code}','审定表{wp_code}-1','审定数')",
         "label": "上年同底稿审定数",
         "description": ""},
    ]
    return cells


def _build_k5_detail_cells() -> list[dict]:
    """K5 预计负债明细块的正确 cells（科目 2801 不是 2701/2241）。"""
    return [
        {"cell_ref": "预计负债_期末未审数", "formula": "=TB('2801','期末余额')",
         "label": "从试算表取预计负债（2801）期末余额",
         "description": "🔴 历史写 2701（长期应付款）是错误科目族"},
        {"cell_ref": "预计负债_期初余额", "formula": "=TB('2801','期初余额')",
         "label": "从试算表取预计负债（2801）期初余额",
         "description": ""},
        {"cell_ref": "本期借方发生额", "formula": "=TB('2801','借方发生额')",
         "label": "从试算表取预计负债本期借方发生额（冲销/支付）",
         "description": ""},
        {"cell_ref": "本期贷方发生额", "formula": "=TB('2801','贷方发生额')",
         "label": "从试算表取预计负债本期贷方发生额（计提）",
         "description": ""},
    ]


def apply_fixes(data: dict) -> list[str]:
    """对 mappings 列表就地修正，返回变更日志。"""
    mappings = data["mappings"]
    changes: list[str] = []

    # Pass 1: Remove orphans K14~K18
    orphans = [i for i, x in enumerate(mappings)
               if x.get("wp_code") in ORPHAN_WP_CODES]
    for i in reversed(orphans):
        block = mappings[i]
        changes.append(f"REMOVE orphan: {block['wp_code']} | {block.get('wp_name','')}")
        del mappings[i]

    # Pass 2: Fix main adjudication blocks for K3~K13
    for x in mappings:
        wc = x.get("wp_code", "")
        if wc not in CORRECT_ACCOUNTS:
            continue
        expected_acct = CORRECT_ACCOUNTS[wc]
        current_accts = x.get("account_codes", [])
        current_name = x.get("wp_name", "")
        cells = x.get("cells") or x.get("entries") or []

        # Identify if this is the main adjudication block (has TB+ADJ formulas with wrong code)
        is_main = any("ADJ(" in (c.get("formula") or "") for c in cells)
        # K5 detail block: has "预计负债" in wp_name and no ADJ
        is_k5_detail = (wc == "K5" and not is_main and
                        any(c for c in current_accts if c in K5_DETAIL_WRONG_CODES))
        # K3 detail (其他应付款明细): correct account 2241, has AUX formulas — leave as-is
        is_k3_detail = (wc == "K3" and not is_main and "2241" in current_accts)

        if is_k3_detail:
            continue  # K3 明细块科目码本就正确

        if is_k5_detail:
            # Fix K5 detail block
            if current_accts != ["2801"]:
                changes.append(f"FIX K5 detail: account_codes {current_accts} → ['2801']")
                x["account_codes"] = ["2801"]
            # Fix cells
            new_cells = _build_k5_detail_cells()
            if cells != new_cells:
                changes.append(f"FIX K5 detail: rewrite {len(cells)} cells → {len(new_cells)} cells")
                x["cells"] = new_cells
            continue

        if not is_main:
            continue  # Skip non-adjudication blocks (K8 月度明细 / K8 分析程序 etc.)

        # Fix wp_name
        correct_name = CORRECT_WP_NAMES.get(wc, "")
        if correct_name and current_name != correct_name:
            changes.append(f"FIX {wc}: wp_name '{current_name}' → '{correct_name}'")
            x["wp_name"] = correct_name

        # Fix account_codes
        if expected_acct is None:
            # Should not have TB() — but keep block with empty cells for PREV()
            new_accts: list[str] = []
            if current_accts != new_accts:
                changes.append(f"FIX {wc}: account_codes {current_accts} → [] (宁缺勿造)")
                x["account_codes"] = new_accts
            # Remove TB/ADJ cells, keep only PREV
            new_cells = [c for c in cells if "PREV(" in (c.get("formula") or "")]
            if not new_cells:
                new_cells = [{"cell_ref": "上年审定数",
                              "formula": f"=PREV('{wc}','审定表{wc}-1','审定数')",
                              "label": "上年同底稿审定数", "description": ""}]
            if cells != new_cells:
                changes.append(f"FIX {wc}: strip TB/ADJ cells → keep {len(new_cells)} PREV-only")
                x["cells"] = new_cells
        else:
            # Fix account_codes
            if expected_acct not in str(current_accts):
                new_accts_list = [expected_acct]
                changes.append(f"FIX {wc}: account_codes {current_accts} → {new_accts_list}")
                x["account_codes"] = new_accts_list

            # Rebuild cells with correct account
            new_cells = _build_correct_cells(wc, expected_acct)
            # Check if current cells reference wrong codes
            has_wrong = any(
                expected_acct not in (c.get("formula") or "")
                for c in cells
                if "TB(" in (c.get("formula") or "") or "ADJ(" in (c.get("formula") or "")
            )
            if has_wrong:
                changes.append(f"FIX {wc}: rewrite {len(cells)} cells (wrong code → {expected_acct})")
                x["cells"] = new_cells

    # Pass 3: Clean pathological ranges in K6
    for x in mappings:
        if x.get("wp_code") != "K6":
            continue
        cells = x.get("cells") or x.get("entries") or []
        for c in cells:
            f = c.get("formula") or ""
            if "TB_SUM('1481~2331')" in f:
                changes.append(f"FIX K6: remove pathological TB_SUM('1481~2331') in {c.get('cell_ref','')}")
                c["formula"] = ""
                c["description"] = (c.get("description") or "") + " [removed: TB_SUM('1481~2331') 跨科目大类病态区间]"

    # Pass 4: Fix K8 附加块的病态区间 TB_SUM('6601~6603')
    for x in mappings:
        if x.get("wp_code") != "K8":
            continue
        cells = x.get("cells") or x.get("entries") or []
        for c in cells:
            f = c.get("formula") or ""
            if "TB_SUM('6601~6603')" in f:
                # Replace with single-code: 这个块是 K8 分析程序，应只取 6601
                new_f = f.replace("TB_SUM('6601~6603','期末余额')", "=TB('6601','期末余额')")
                new_f = new_f.replace("TB_SUM('6601~6603'", "TB('6601'")
                if new_f != f:
                    changes.append(f"FIX K8 analysis: TB_SUM('6601~6603') → TB('6601') in {c.get('cell_ref','')}")
                    c["formula"] = new_f

    # Pass 5: Add WP() linkage (审定表 ← 明细表/检查表勾稽)
    # 铁律：明细表块禁含 WP() 防成环；审定表块可引明细表
    WP_LINKAGE: dict[str, list[dict]] = {
        "K3": [
            {"cell_ref": "明细表期末合计", "formula": "=WP('K3','明细表K3-2','期末余额合计')",
             "label": "审定表与 K3-2 明细表期末合计勾稽", "description": "🔴 反向不可：K3-2 禁引 WP() 防循环"},
        ],
        "K5": [
            {"cell_ref": "明细表期末合计", "formula": "=WP('K5','明细表K5-2','期末余额合计')",
             "label": "审定表与 K5-2 明细表期末合计勾稽", "description": ""},
        ],
        "K7": [
            {"cell_ref": "明细表期末合计", "formula": "=WP('K7','明细表K7-2','期末余额合计')",
             "label": "审定表与 K7-2 明细表期末合计勾稽", "description": ""},
        ],
        "K8": [
            {"cell_ref": "明细表本期合计", "formula": "=WP('K8','明细表K8-2','本期发生额合计')",
             "label": "审定表与 K8-2 明细表本期发生额合计勾稽", "description": ""},
        ],
        "K9": [
            {"cell_ref": "明细表本期合计", "formula": "=WP('K9','明细表K9-2','本期发生额合计')",
             "label": "审定表与 K9-2 明细表本期发生额合计勾稽", "description": ""},
        ],
    }
    for x in mappings:
        wc = x.get("wp_code", "")
        if wc not in WP_LINKAGE:
            continue
        cells = x.get("cells") or x.get("entries") or []
        is_main = any("ADJ(" in (c.get("formula") or "") or "PREV(" in (c.get("formula") or "")
                       for c in cells)
        if not is_main:
            continue
        for wp_entry in WP_LINKAGE[wc]:
            # Check if already present
            existing_refs = {c.get("cell_ref") for c in cells}
            if wp_entry["cell_ref"] in existing_refs:
                continue
            cells.append(wp_entry)
            changes.append(f"ADD WP: {wc} | {wp_entry['cell_ref']} → {wp_entry['formula']}")
        x["cells"] = cells

    return changes


def main():
    parser = argparse.ArgumentParser(description="K 循环公式预设修正幂等脚本")
    parser.add_argument("--apply", action="store_true", help="执行修正并写盘")
    parser.add_argument("--check", action="store_true", help="检查后以 exit code 报告")
    args = parser.parse_args()

    data = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    changes = apply_fixes(data)

    if not changes:
        print("✅ 无需变更（已是最新）")
        sys.exit(0)

    print(f"{'[DRY-RUN] ' if not args.apply else ''}变更清单 ({len(changes)} 项):")
    for c in changes:
        print(f"  • {c}")

    if args.apply:
        _DATA_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"\n✅ 已写盘: {_DATA_PATH}")
    elif args.check:
        print(f"\n❌ 有 {len(changes)} 项欠账")
        sys.exit(1)
    else:
        print(f"\n⚠️  DRY-RUN 模式，使用 --apply 执行修正")


if __name__ == "__main__":
    main()
