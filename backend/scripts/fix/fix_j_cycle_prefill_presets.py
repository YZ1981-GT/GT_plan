"""J 类公式预设修订（幂等脚本）。

修订内容：
1. J2 两块：`account_codes` ['2611']→['2705']；所有 TB/ADJ 公式里的 '2611'→'2705'
2. J1 `分析程序J1-3`：源 xlsx 无此 tab，实为 `调整分录汇总表J1-3`
3. J3 `审定表J3-1`：源 xlsx 无此 tab；实为 `股份支付情况表J3-1`
4. J1-2/J1-7 的 12 条 AUX：删除硬编码具体成本中心编码（010102 等，属某项目污染）
5. J1-1 补 WP 联动（←J1-2/J1-6）；J2-1 补 WP 联动（←J2-2）

用法：
    python scripts/fix/fix_j_cycle_prefill_presets.py --dry-run   # 预览
    python scripts/fix/fix_j_cycle_prefill_presets.py --check     # CI 验证（有欠账 exit 1）
    python scripts/fix/fix_j_cycle_prefill_presets.py             # 执行写入

spec: .kiro/specs/j-cycle-four-table-extraction-and-disclosure-alignment/
      Requirements 4.1~4.6
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MAPPING_FILE = Path(__file__).resolve().parents[2] / "data" / "prefill_formula_mapping.json"


def _load():
    return json.loads(MAPPING_FILE.read_text("utf-8"))


def _save(doc):
    MAPPING_FILE.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _fix(doc) -> list[str]:
    """Apply fixes, return list of change descriptions."""
    changes: list[str] = []
    m = doc["mappings"]

    for b in m:
        wp = b["wp_code"]

        # ── Fix 1: J2 科目码 2611→2705 ─────────────────────────────────────
        if wp == "J2" and "2611" in b.get("account_codes", []):
            b["account_codes"] = ["2705"]
            changes.append(f"J2/{b['sheet']}: account_codes ['2611']→['2705']")
            for c in b["cells"]:
                if "2611" in c.get("formula", ""):
                    old = c["formula"]
                    c["formula"] = old.replace("2611", "2705")
                    changes.append(f"  cell {c['cell_ref']}: {old} → {c['formula']}")
                if "2611" in c.get("description", ""):
                    c["description"] = c["description"].replace("2611", "2705")

        # ── Fix 2: J1 sheet 名纠正 ─────────────────────────────────────────
        if wp == "J1" and b["sheet"] == "分析程序J1-3":
            b["sheet"] = "调整分录汇总表J1-3"
            changes.append("J1: sheet '分析程序J1-3' → '调整分录汇总表J1-3'")

        # ── Fix 3: J3 sheet 名纠正 ─────────────────────────────────────────
        if wp == "J3" and b["sheet"] == "审定表J3-1":
            b["sheet"] = "股份支付情况表J3-1"
            changes.append("J3: sheet '审定表J3-1' → '股份支付情况表J3-1'")

        # ── Fix 4: J1-2/J1-7 删硬编码成本中心 AUX ──────────────────────────
        if wp == "J1" and b["sheet"] in ("明细表J1-2 ", "分配情况检查表J1-7"):
            before = len(b["cells"])
            b["cells"] = [
                c
                for c in b["cells"]
                if not (c.get("formula_type") == "AUX" and "成本中心" in c.get("formula", ""))
            ]
            removed = before - len(b["cells"])
            if removed > 0:
                changes.append(
                    f"J1/{b['sheet']}: 删 {removed} 条硬编码成本中心 AUX（010102 等项目污染）"
                )

    # ── Fix 5: J1-1 补 WP 联动 ─────────────────────────────────────────────
    for b in m:
        if b["wp_code"] == "J1" and b["sheet"] == "审定表J1-1":
            existing_refs = {c["cell_ref"] for c in b["cells"]}
            new_cells = []
            if "明细表J1-2期末合计" not in existing_refs:
                new_cells.append(
                    {
                        "cell_ref": "明细表J1-2期末合计",
                        "formula": "=WP('J1','明细表J1-2 ','期末审定合计')",
                        "formula_type": "WP",
                        "description": "从明细表J1-2取期末审定合计（底稿间联动）",
                    }
                )
            if "计提情况J1-6本期贷方" not in existing_refs:
                new_cells.append(
                    {
                        "cell_ref": "计提情况J1-6本期贷方",
                        "formula": "=WP('J1','计提情况检查表J1-6','本期贷方合计')",
                        "formula_type": "WP",
                        "description": "从计提情况检查表J1-6取本期贷方合计",
                    }
                )
            if new_cells:
                b["cells"].extend(new_cells)
                changes.append(f"J1/审定表J1-1: 补 {len(new_cells)} 条 WP() 联动")

    for b in m:
        if b["wp_code"] == "J2" and b["sheet"] == "审定表J2-1":
            existing_refs = {c["cell_ref"] for c in b["cells"]}
            if "明细表J2-2期末合计" not in existing_refs:
                b["cells"].append(
                    {
                        "cell_ref": "明细表J2-2期末合计",
                        "formula": "=WP('J2','明细表J2-2','期末审定合计')",
                        "formula_type": "WP",
                        "description": "从明细表J2-2取期末审定合计（底稿间联动）",
                    }
                )
                changes.append("J2/审定表J2-1: 补 1 条 WP() 联动")

    return changes


def _check(doc) -> list[str]:
    """验证修订后无残留问题。"""
    issues: list[str] = []
    m = doc["mappings"]
    for b in m:
        wp = b["wp_code"]
        if wp not in ("J1", "J2", "J3"):
            continue
        # 科目码合法性
        if wp == "J2" and "2611" in b.get("account_codes", []):
            issues.append(f"J2/{b['sheet']}: account_codes 仍含 2611")
        if wp == "J2":
            for c in b["cells"]:
                if "2611" in c.get("formula", ""):
                    issues.append(f"J2/{b['sheet']}/{c['cell_ref']}: 公式仍含 2611")
        # sheet 名存在性
        if wp == "J1" and b["sheet"] == "分析程序J1-3":
            issues.append("J1: sheet '分析程序J1-3' 在源 xlsx 不存在")
        if wp == "J3" and b["sheet"] == "审定表J3-1":
            issues.append("J3: sheet '审定表J3-1' 在源 xlsx 不存在")
        # AUX 硬编码成本中心
        if wp == "J1" and b["sheet"] in ("明细表J1-2 ", "分配情况检查表J1-7"):
            for c in b["cells"]:
                if c.get("formula_type") == "AUX" and "成本中心" in c.get("formula", ""):
                    issues.append(f"J1/{b['sheet']}/{c['cell_ref']}: 残留硬编码成本中心 AUX")
        # 审定表必须有 WP 联动
        if wp == "J1" and b["sheet"] == "审定表J1-1":
            refs = {c["cell_ref"] for c in b["cells"]}
            if "明细表J1-2期末合计" not in refs:
                issues.append("J1/审定表J1-1: 缺 WP 联动 (J1-2)")
        if wp == "J2" and b["sheet"] == "审定表J2-1":
            refs = {c["cell_ref"] for c in b["cells"]}
            if "明细表J2-2期末合计" not in refs:
                issues.append("J2/审定表J2-1: 缺 WP 联动 (J2-2)")
    return issues


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    doc = _load()

    if args.check:
        issues = _check(doc)
        if issues:
            print(f"❌ {len(issues)} 项欠账：")
            for i in issues:
                print(f"  • {i}")
            sys.exit(1)
        else:
            print("✅ J 类预设 --check 通过（0 项欠账）")
            sys.exit(0)

    changes = _fix(doc)
    if not changes:
        print("✅ 无需修改（已是最终状态）")
        return

    for c in changes:
        print(f"  {c}")

    if args.dry_run:
        print(f"\n🔍 dry-run 完毕，共 {len(changes)} 项变更未写入")
    else:
        _save(doc)
        print(f"\n✅ 已写入 {MAPPING_FILE.name}（{len(changes)} 项变更）")


if __name__ == "__main__":
    main()
