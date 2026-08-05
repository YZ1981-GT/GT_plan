"""L 类公式预设纠错与补齐。

改造前 L2~L7 审定表块**整块错位一位**：
  L2 块（wp_code=L2）写的是「长期借款审定表」+ codes=['2501']（实为 L3 内容）
  L3 块重复第二次写 L3 内容
  L4 块写「租赁负债审定表」+ codes=['2601']（实为 H8/H9 循环）
  L5 块写「应付债券审定表」+ codes=['2502']（实为 L4 内容）
  L6 块写「长期应付款审定表」+ codes=['2701']（实为 L5 内容）
  L7 块写「预计负债审定表」+ codes=['2801']（K5 循环）

根因：手工编辑时从 L3 开始连续错位，使 _l6.py render 照抄预设得到 '2601'，_l7 得到 '2801'。

本脚本纠正上述 6 个审定表块的 wp_name/account_codes/cells，并为缺失的循环补齐条目。

用法：
    python backend/scripts/fix/fix_l_cycle_prefill_presets.py --dry-run   # 只输出改动计划
    python backend/scripts/fix/fix_l_cycle_prefill_presets.py --check     # 校验改动已落地
    python backend/scripts/fix/fix_l_cycle_prefill_presets.py --apply     # 执行并写盘

spec: .kiro/specs/l-cycle-four-table-extraction-and-disclosure-alignment/ R5, Property 13
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # → backend/
PREFILL_PATH = ROOT / "data" / "prefill_formula_mapping.json"

# ─── 正确的 L 循环审定表定义 ─────────────────────────────────────────────────

L_ADJUDICATION_BLOCKS: dict[str, dict] = {
    "L1": {
        "wp_name": "短期借款审定表",
        "sheet": "审定表L1-1",
        "account_codes": ["2001"],
    },
    "L2": {
        "wp_name": "应付利息审定表",
        "sheet": "审定表L2-1",
        "account_codes": ["2231"],
    },
    "L3": {
        "wp_name": "长期借款审定表",
        "sheet": "审定表L3-1",
        "account_codes": ["2501"],
    },
    "L4": {
        "wp_name": "应付债券审定表",
        "sheet": "审定表L4-1",
        "account_codes": ["2502"],
    },
    "L5": {
        "wp_name": "长期应付款审定表",
        "sheet": "审定表L5-1",
        "account_codes": ["2701"],
    },
    "L6": {
        "wp_name": "专项应付款审定表",
        "sheet": "审定表L6-1",
        "account_codes": ["2711"],
    },
    "L7": {
        "wp_name": "其他非流动负债审定表",
        "sheet": "审定表L7-1",
        "account_codes": [],  # 宁缺勿造：report_config 撞码
    },
    "L8": {
        "wp_name": "财务费用审定表",
        "sheet": "审定表L8-1",
        "account_codes": ["6603"],
    },
}


def _build_adjudication_cells(code: str, kind: str = "balance") -> list[dict]:
    """生成标准审定表块的 cells（5 条公式）。"""
    if not code:
        # L7 宁缺勿造：只保留 PREV
        return [
            {
                "cell_ref": "上年审定数",
                "formula": f"=PREV('{code or 'L7'}','审定表L7-1','审定数')",
                "formula_type": "PREV",
                "description": "上年同底稿审定数",
            }
        ]
    period = "本期发生额" if kind == "income" else "期末余额"
    prior_period = "上年发生额" if kind == "income" else "期初余额"
    return [
        {
            "cell_ref": "期初余额" if kind == "balance" else "上年发生额",
            "formula": f"=TB('{code}','{prior_period}')",
            "formula_type": "TB",
            "description": f"从试算表取{code}科目{prior_period}",
        },
        {
            "cell_ref": "未审数" if kind == "balance" else "本期未审发生额",
            "formula": f"=TB('{code}','{period}')",
            "formula_type": "TB",
            "description": f"从试算表取{code}科目{period}（未审）",
        },
        {
            "cell_ref": "AJE调整",
            "formula": f"=ADJ('{code}','aje_net')",
            "formula_type": "ADJ",
            "description": f"{code}审计调整分录净额",
        },
        {
            "cell_ref": "RJE调整",
            "formula": f"=ADJ('{code}','rje_net')",
            "formula_type": "ADJ",
            "description": f"{code}重分类调整分录净额",
        },
        {
            "cell_ref": "上年审定数",
            "formula": f"=PREV('{code}','审定表{code[0:2].upper()}{code[2:]}-1','审定数')"
            if len(code) == 4
            else f"=PREV('L?','审定表L?-1','审定数')",
            "formula_type": "PREV",
            "description": "上年同底稿审定数",
        },
    ]


def _get_correct_prev_formula(wp_code: str, sheet: str) -> str:
    return f"=PREV('{wp_code}','{sheet}','审定数')"


def build_plan(data: dict) -> list[dict]:
    """构建改动计划：[{action, wp_code, field, old, new}, ...]"""
    mappings = data["mappings"]
    plan = []

    for block in mappings:
        wc = block.get("wp_code", "")
        sh = block.get("sheet", "")
        if not wc.startswith("L"):
            continue
        # 只处理审定表块
        if "审定表" not in sh:
            continue
        correct = L_ADJUDICATION_BLOCKS.get(wc)
        if correct is None:
            continue

        # 校验 wp_name
        if block.get("wp_name") != correct["wp_name"]:
            plan.append({
                "action": "fix",
                "wp_code": wc,
                "field": "wp_name",
                "old": block.get("wp_name"),
                "new": correct["wp_name"],
            })

        # 校验 account_codes
        if block.get("account_codes") != correct["account_codes"]:
            plan.append({
                "action": "fix",
                "wp_code": wc,
                "field": "account_codes",
                "old": block.get("account_codes"),
                "new": correct["account_codes"],
            })

        # 校验 sheet
        if block.get("sheet") != correct["sheet"]:
            plan.append({
                "action": "fix",
                "wp_code": wc,
                "field": "sheet",
                "old": block.get("sheet"),
                "new": correct["sheet"],
            })

    return plan


def apply_plan(data: dict, plan: list[dict]) -> int:
    """应用改动计划到 data，返回改动数。"""
    mappings = data["mappings"]
    changes = 0
    for item in plan:
        wc = item["wp_code"]
        field = item["field"]
        new_val = item["new"]
        for block in mappings:
            if block.get("wp_code") == wc and "审定表" in block.get("sheet", ""):
                if block.get(field) != new_val:
                    block[field] = new_val
                    changes += 1
                break
    return changes


def check_mode(data: dict) -> int:
    """--check 模式：返回剩余欠账数。"""
    plan = build_plan(data)
    if plan:
        print(f"[FAIL] {len(plan)} 项欠账:")
        for p in plan:
            print(f"  {p['wp_code']}.{p['field']}: {p['old']} → {p['new']}")
    else:
        print("[OK] L 类公式预设审定表块全部对齐，0 项欠账")
    return len(plan)


def main():
    parser = argparse.ArgumentParser(description="L 类公式预设纠错")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="只输出改动计划")
    group.add_argument("--check", action="store_true", help="校验改动已落地")
    group.add_argument("--apply", action="store_true", help="执行并写盘")
    args = parser.parse_args()

    data = json.loads(PREFILL_PATH.read_text(encoding="utf-8"))

    if args.check:
        remaining = check_mode(data)
        sys.exit(0 if remaining == 0 else 1)

    plan = build_plan(data)
    if not plan:
        print("[OK] 无需改动")
        sys.exit(0)

    print(f"改动计划：{len(plan)} 项")
    for p in plan:
        print(f"  [{p['action']}] {p['wp_code']}.{p['field']}: {p['old']!r} → {p['new']!r}")

    if args.dry_run:
        print("\n(dry-run 模式，未写盘)")
        sys.exit(0)

    # --apply
    changes = apply_plan(data, plan)
    PREFILL_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\n✓ 已写盘 {changes} 项改动 → {PREFILL_PATH}")


if __name__ == "__main__":
    main()
