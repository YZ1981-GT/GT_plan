#!/usr/bin/env python
"""修正 I 类公式预设的科目码与 sheet 引用（幂等）。

Wave 2 修订：I 类 18 个块中存在系统性贴错标签问题，
由上一步诊断确认（tmp_i_out2.txt）。

主要错误：
- I2 审定表：wp_name='商誉审定表' + account_codes=['1711'] → 开发支出审定表 + ['1704']
- I3 审定表：wp_name='长期待摊费用审定表' + ['1801'] → 商誉审定表 + ['1711']
- I4 审定表：wp_name='开发支出审定表' + ['1703'] → 长期待摊费用审定表 + ['1801']
- I5 审定表：account_codes=['1811']（递延所得税资产属 N1）→ []
- I6 审定表：account_codes=['6602'] → ['6604']
- I1 审定表：account_codes 缺 '1703'
- I3 明细块：引用 1712（account_chart 无此码）
- I2 明细块：account_codes=['1801','6602'] → ['1704','5301']
- I4 明细块：account_codes=['1801','1811'] → ['1801']（删 1811）
- I6 月度明细块：account_codes=['6602'] → ['6604']
- I1 分析程序块：引用不存在的 sheet 分析程序I1-3 → 整块删除
- I2 资本化判断块：account_codes=['1801'] → ['1704']
- I1 审定表：PREV sheet 引用 '审定表I1-1' → '审定表I1'

Usage::

    python backend/scripts/fix/fix_i_cycle_prefill_presets.py --dry-run
    python backend/scripts/fix/fix_i_cycle_prefill_presets.py --apply
    python backend/scripts/fix/fix_i_cycle_prefill_presets.py --check

spec: .kiro/specs/i-cycle-four-table-extraction-and-disclosure-alignment/
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parent.parent.parent
MAPPING_PATH = _BACKEND / "data" / "prefill_formula_mapping.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _blocks(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return doc["mappings"]


def _find_block(doc: dict[str, Any], wp_code: str, sheet: str) -> dict[str, Any] | None:
    for b in _blocks(doc):
        if b.get("wp_code") == wp_code and b.get("sheet") == sheet:
            return b
    return None


def _replace_code_in_formula(formula: str, old: str, new: str) -> str:
    """Replace account code in formula expressions like TB('old',...) → TB('new',...)."""
    return formula.replace(f"'{old}'", f"'{new}'")


def _remove_cells_with_code(block: dict[str, Any], code: str) -> int:
    """Remove cells whose formula references the given code. Returns count removed."""
    cells = block.get("cells", [])
    before = len(cells)
    block["cells"] = [c for c in cells if f"'{code}'" not in c.get("formula", "")]
    return before - len(block["cells"])


# ---------------------------------------------------------------------------
# apply_fixes: the idempotent correction logic
# ---------------------------------------------------------------------------

def apply_fixes(doc: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Apply all I-cycle corrections. Returns (modified_doc, list_of_changes)."""
    changes: list[str] = []

    # --- 1. I1 审定表：account_codes 补 '1703'；PREV sheet 引用修正 ---
    b = _find_block(doc, "I1", "审定表I1-1")
    if b:
        codes = b.get("account_codes", [])
        if "1703" not in codes:
            codes.append("1703")
            b["account_codes"] = codes
            changes.append("I1 审定表: account_codes 补 '1703'")
        # Fix PREV sheet reference: '审定表I1-1' → '审定表I1'
        for c in b.get("cells", []):
            f = c.get("formula", "")
            if "PREV('I1','审定表I1-1'" in f:
                c["formula"] = f.replace("PREV('I1','审定表I1-1'", "PREV('I1','审定表I1'")
                changes.append("I1 审定表: PREV sheet '审定表I1-1' → '审定表I1'")

    # --- 2. I2 审定表：wp_name→开发支出审定表; account_codes→['1704']; TB('1711')→TB('1704') ---
    b = _find_block(doc, "I2", "审定表I2-1")
    if b:
        if b.get("wp_name") != "开发支出审定表":
            b["wp_name"] = "开发支出审定表"
            changes.append("I2 审定表: wp_name → '开发支出审定表'")
        if b.get("account_codes") != ["1704"]:
            b["account_codes"] = ["1704"]
            changes.append("I2 审定表: account_codes → ['1704']")
        for c in b.get("cells", []):
            f = c.get("formula", "")
            if "'1711'" in f:
                c["formula"] = _replace_code_in_formula(f, "1711", "1704")
                changes.append(f"I2 审定表: TB('1711') → TB('1704') in {c['cell_ref']}")


    # --- 3. I3 审定表：wp_name→商誉审定表; account_codes→['1711']; TB('1801')→TB('1711') ---
    b = _find_block(doc, "I3", "审定表I3-1")
    if b:
        if b.get("wp_name") != "商誉审定表":
            b["wp_name"] = "商誉审定表"
            changes.append("I3 审定表: wp_name → '商誉审定表'")
        if b.get("account_codes") != ["1711"]:
            b["account_codes"] = ["1711"]
            changes.append("I3 审定表: account_codes → ['1711']")
        for c in b.get("cells", []):
            f = c.get("formula", "")
            if "'1801'" in f:
                c["formula"] = _replace_code_in_formula(f, "1801", "1711")
                changes.append(f"I3 审定表: TB('1801') → TB('1711') in {c['cell_ref']}")

    # --- 4. I4 审定表：wp_name→长期待摊费用审定表; account_codes→['1801']; TB('1703')→TB('1801') ---
    b = _find_block(doc, "I4", "审定表I4-1")
    if b:
        if b.get("wp_name") != "长期待摊费用审定表":
            b["wp_name"] = "长期待摊费用审定表"
            changes.append("I4 审定表: wp_name → '长期待摊费用审定表'")
        if b.get("account_codes") != ["1801"]:
            b["account_codes"] = ["1801"]
            changes.append("I4 审定表: account_codes → ['1801']")
        for c in b.get("cells", []):
            f = c.get("formula", "")
            if "'1703'" in f:
                c["formula"] = _replace_code_in_formula(f, "1703", "1801")
                changes.append(f"I4 审定表: TB('1703') → TB('1801') in {c['cell_ref']}")

    # --- 5. I5 审定表：wp_name→其他非流动资产审定表; account_codes→[]; 删 TB('1811') cells ---
    b = _find_block(doc, "I5", "审定表I5-1")
    if b:
        if b.get("wp_name") != "其他非流动资产审定表":
            b["wp_name"] = "其他非流动资产审定表"
            changes.append("I5 审定表: wp_name → '其他非流动资产审定表'")
        if b.get("account_codes") != []:
            b["account_codes"] = []
            changes.append("I5 审定表: account_codes → [] (1811 属 N1 循环)")
        removed = _remove_cells_with_code(b, "1811")
        if removed:
            changes.append(f"I5 审定表: 删除 {removed} 条引用 1811 的 cells")


    # --- 6. I6 审定表：wp_name→研发费用审定表; account_codes→['6604']; TB('6602')→TB('6604') ---
    b = _find_block(doc, "I6", "审定表I6-1")
    if b:
        if b.get("wp_name") != "研发费用审定表":
            b["wp_name"] = "研发费用审定表"
            changes.append("I6 审定表: wp_name → '研发费用审定表'")
        if b.get("account_codes") != ["6604"]:
            b["account_codes"] = ["6604"]
            changes.append("I6 审定表: account_codes → ['6604']")
        for c in b.get("cells", []):
            f = c.get("formula", "")
            if "'6602'" in f:
                c["formula"] = _replace_code_in_formula(f, "6602", "6604")
                changes.append(f"I6 审定表: TB('6602') → TB('6604') in {c['cell_ref']}")

    # --- 7. I2 明细块：account_codes→['1704','5301']; TB('1801')→TB('1704') ---
    b = _find_block(doc, "I2", "明细表I2-2")
    if b:
        if b.get("account_codes") != ["1704", "5301"]:
            b["account_codes"] = ["1704", "5301"]
            changes.append("I2 明细表: account_codes → ['1704','5301']")
        # wp_name fix: should be 开发支出明细表
        if b.get("wp_name") != "开发支出明细表":
            b["wp_name"] = "开发支出明细表"
            changes.append("I2 明细表: wp_name → '开发支出明细表'")
        for c in b.get("cells", []):
            f = c.get("formula", "")
            if "'1801'" in f:
                c["formula"] = _replace_code_in_formula(f, "1801", "1704")
                changes.append(f"I2 明细表: TB('1801') → TB('1704') in {c['cell_ref']}")
        # TB('6602') 保留（用于与 I6 勾稽），不改

    # --- 8. I3 明细块：删除引用 1712 的 cells（account_chart 无此码） ---
    b = _find_block(doc, "I3", "明细表I3-2")
    if b:
        removed = _remove_cells_with_code(b, "1712")
        if removed:
            changes.append(f"I3 明细表: 删除 {removed} 条引用 1712 的 cells")
        # Also fix account_codes: remove '1712'
        codes = b.get("account_codes", [])
        if "1712" in codes:
            codes.remove("1712")
            b["account_codes"] = codes
            changes.append("I3 明细表: account_codes 删除 '1712'")


    # --- 9. I4 明细块：account_codes→['1801']（删 1811）; 删 TB('1811') cells ---
    b = _find_block(doc, "I4", "明细表I4-2")
    if b:
        if b.get("account_codes") != ["1801"]:
            b["account_codes"] = ["1801"]
            changes.append("I4 明细表: account_codes → ['1801'] (删 1811)")
        removed = _remove_cells_with_code(b, "1811")
        if removed:
            changes.append(f"I4 明细表: 删除 {removed} 条引用 1811 的 cells")

    # --- 10. I6 月度明细块：account_codes→['6604']; TB/LEDGER('6602')→('6604') ---
    b = _find_block(doc, "I6", "明细表I6-2")
    if b:
        if b.get("account_codes") != ["6604"]:
            b["account_codes"] = ["6604"]
            changes.append("I6 月度明细: account_codes → ['6604']")
        for c in b.get("cells", []):
            f = c.get("formula", "")
            if "'6602'" in f:
                c["formula"] = _replace_code_in_formula(f, "6602", "6604")
                changes.append(f"I6 月度明细: ('6602') → ('6604') in {c['cell_ref']}")

    # --- 11. I1 分析程序块：整块删除（引用不存在的 sheet + 病态 TB_SUM） ---
    idx_to_remove = None
    for i, blk in enumerate(_blocks(doc)):
        if blk.get("wp_code") == "I1" and blk.get("sheet") == "分析程序I1-3":
            idx_to_remove = i
            break
    if idx_to_remove is not None:
        _blocks(doc).pop(idx_to_remove)
        changes.append("I1 分析程序块: 整块删除（sheet '分析程序I1-3' 不存在 + 病态 TB_SUM）")

    # --- 12. I2 资本化判断块：account_codes→['1704'] ---
    b = _find_block(doc, "I2", "研发项目资本化时点判断I2-6")
    if b:
        if b.get("account_codes") != ["1704"]:
            b["account_codes"] = ["1704"]
            changes.append("I2 资本化判断块: account_codes → ['1704']")

    return doc, changes


# ---------------------------------------------------------------------------
# check: verify no remaining errors
# ---------------------------------------------------------------------------

def check(doc: dict[str, Any]) -> list[str]:
    """Check for remaining I-cycle preset errors. Returns list of issues."""
    issues: list[str] = []

    # I1 审定表
    b = _find_block(doc, "I1", "审定表I1-1")
    if b:
        codes = b.get("account_codes", [])
        if "1703" not in codes:
            issues.append("I1 审定表: account_codes 缺 '1703'")
        formulas = " ".join(c.get("formula", "") for c in b.get("cells", []))
        if "审定表I1-1'" in formulas:
            issues.append("I1 审定表: PREV 仍引用 '审定表I1-1'（应为 '审定表I1'）")
    else:
        issues.append("I1 审定表块不存在")

    # I2 审定表
    b = _find_block(doc, "I2", "审定表I2-1")
    if b:
        if b.get("wp_name") != "开发支出审定表":
            issues.append(f"I2 审定表: wp_name='{b.get('wp_name')}' (应为 '开发支出审定表')")
        if b.get("account_codes") != ["1704"]:
            issues.append(f"I2 审定表: account_codes={b.get('account_codes')} (应为 ['1704'])")
        formulas = " ".join(c.get("formula", "") for c in b.get("cells", []))
        if "'1711'" in formulas:
            issues.append("I2 审定表: 仍引用 '1711'")
    else:
        issues.append("I2 审定表块不存在")

    # I3 审定表
    b = _find_block(doc, "I3", "审定表I3-1")
    if b:
        if b.get("wp_name") != "商誉审定表":
            issues.append(f"I3 审定表: wp_name='{b.get('wp_name')}' (应为 '商誉审定表')")
        if b.get("account_codes") != ["1711"]:
            issues.append(f"I3 审定表: account_codes={b.get('account_codes')} (应为 ['1711'])")
        formulas = " ".join(c.get("formula", "") for c in b.get("cells", []))
        if "'1801'" in formulas:
            issues.append("I3 审定表: 仍引用 '1801'")
    else:
        issues.append("I3 审定表块不存在")

    # I4 审定表
    b = _find_block(doc, "I4", "审定表I4-1")
    if b:
        if b.get("wp_name") != "长期待摊费用审定表":
            issues.append(f"I4 审定表: wp_name='{b.get('wp_name')}' (应为 '长期待摊费用审定表')")
        if b.get("account_codes") != ["1801"]:
            issues.append(f"I4 审定表: account_codes={b.get('account_codes')} (应为 ['1801'])")
        formulas = " ".join(c.get("formula", "") for c in b.get("cells", []))
        if "'1703'" in formulas:
            issues.append("I4 审定表: 仍引用 '1703'")
    else:
        issues.append("I4 审定表块不存在")


    # I5 审定表
    b = _find_block(doc, "I5", "审定表I5-1")
    if b:
        if b.get("account_codes") != []:
            issues.append(f"I5 审定表: account_codes={b.get('account_codes')} (应为 [])")
        formulas = " ".join(c.get("formula", "") for c in b.get("cells", []))
        if "'1811'" in formulas:
            issues.append("I5 审定表: 仍引用 '1811'")
    else:
        issues.append("I5 审定表块不存在")

    # I6 审定表
    b = _find_block(doc, "I6", "审定表I6-1")
    if b:
        if b.get("account_codes") != ["6604"]:
            issues.append(f"I6 审定表: account_codes={b.get('account_codes')} (应为 ['6604'])")
        formulas = " ".join(c.get("formula", "") for c in b.get("cells", []))
        if "'6602'" in formulas:
            issues.append("I6 审定表: 仍引用 '6602'")
    else:
        issues.append("I6 审定表块不存在")

    # I2 明细块
    b = _find_block(doc, "I2", "明细表I2-2")
    if b:
        if b.get("account_codes") != ["1704", "5301"]:
            issues.append(f"I2 明细表: account_codes={b.get('account_codes')} (应为 ['1704','5301'])")
        formulas = " ".join(c.get("formula", "") for c in b.get("cells", []))
        if "'1801'" in formulas:
            issues.append("I2 明细表: 仍引用 '1801'（应改 '1704'）")

    # I3 明细块
    b = _find_block(doc, "I3", "明细表I3-2")
    if b:
        codes = b.get("account_codes", [])
        if "1712" in codes:
            issues.append("I3 明细表: account_codes 仍含 '1712'")
        formulas = " ".join(c.get("formula", "") for c in b.get("cells", []))
        if "'1712'" in formulas:
            issues.append("I3 明细表: 仍引用 '1712'（account_chart 无此码）")

    # I4 明细块
    b = _find_block(doc, "I4", "明细表I4-2")
    if b:
        if b.get("account_codes") != ["1801"]:
            issues.append(f"I4 明细表: account_codes={b.get('account_codes')} (应为 ['1801'])")
        formulas = " ".join(c.get("formula", "") for c in b.get("cells", []))
        if "'1811'" in formulas:
            issues.append("I4 明细表: 仍引用 '1811'")

    # I6 月度明细
    b = _find_block(doc, "I6", "明细表I6-2")
    if b:
        if b.get("account_codes") != ["6604"]:
            issues.append(f"I6 月度明细: account_codes={b.get('account_codes')} (应为 ['6604'])")
        formulas = " ".join(c.get("formula", "") for c in b.get("cells", []))
        if "'6602'" in formulas:
            issues.append("I6 月度明细: 仍引用 '6602'")

    # I1 分析程序块应已删除
    b = _find_block(doc, "I1", "分析程序I1-3")
    if b is not None:
        issues.append("I1 分析程序块: 仍存在（应已删除，sheet 不存在 + 病态 TB_SUM）")

    # I2 资本化判断块
    b = _find_block(doc, "I2", "研发项目资本化时点判断I2-6")
    if b:
        if b.get("account_codes") != ["1704"]:
            issues.append(f"I2 资本化判断块: account_codes={b.get('account_codes')} (应为 ['1704'])")

    return issues


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="修正 I 类公式预设（幂等）")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="写回修订到 JSON 文件")
    mode.add_argument("--check", action="store_true", help="检查是否有未修正的错误（CI 用）")
    args = ap.parse_args()

    raw = MAPPING_PATH.read_text(encoding="utf-8")
    doc = json.loads(raw)

    if args.check:
        issues = check(doc)
        if issues:
            print(f"[FAIL] {len(issues)} 个未修正的 I 类预设错误：")
            for iss in issues:
                print(f"  - {iss}")
            return 1
        print("[OK] I 类公式预设校验通过（0 个错误）")
        return 0

    # Default: dry-run (print changes without writing)
    doc, changes = apply_fixes(doc)

    if not changes:
        print("无需修改（已对齐）")
    else:
        print(f"修订方案（{len(changes)} 处变更）：")
        for ch in changes:
            print(f"  - {ch}")

    # Post-apply validation
    issues = check(doc)
    if issues:
        print(f"\n[ERROR] 修订后仍有 {len(issues)} 个未修正错误：")
        for iss in issues:
            print(f"  - {iss}")
        return 1

    if not args.apply:
        print("\n[dry-run] 未写文件。使用 --apply 写入。")
        return 0

    # Write back
    if changes:
        trailing = "\n" if raw.endswith("\n") else ""
        MAPPING_PATH.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2) + trailing,
            encoding="utf-8",
        )
        print(f"\n已写入 {MAPPING_PATH}")

    print("[OK] I 类公式预设修正完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
