"""纠正 wp_account_mapping.json 里 E0 子底稿的名称（幂等）。

## 缺陷

`wp_account_mapping.json` 的 E0-3 / E0-4 / E0-5 三条 `wp_name` 是 **D0 循环口径的错名**
（跟函控制 / 差异调节 / 替代程序），显然是照抄 D0 的五张表模式：

    D0-3 跟函函证过程控制D0-3   → 跟函控制 ✓
    D0-4 函证差异调节表D0-4     → 差异调节 ✓
    D0-5 合同负债及销售替代程序D0-5 → 替代程序 ✓

但 E0 的编号语义完全不同（源模板 `底稿目录` D/E/F 三列是唯一裁决者）：

    E0A  函证程序表
    E0-1 函证结果汇总表
    E0-2 核实被函证单位信息
    E0-3 货币资金发函记录表        ← 不是「跟函控制」
    E0-4 借款发函记录表            ← 不是「差异调节」
    E0-5 应付银行承兑汇票发函记录表 ← 不是「替代程序」
    E0-6 理财产品发函记录表
    E0-7 跟函函证过程控制          ← E0 的跟函控制在这里
    E0-8 函证程序舞弊风险评价表

E0 **没有**「差异调节」「替代程序」两张 sheet。

## 影响

`chain_orchestrator._create_wp_from_mapping` 用本文件的 `wp_name` 建 `wp_index`
（`resolve_wp_name(code, code_name_map[code])`），故底稿目录导航里 E0-3/E0-4/E0-5
显示为跟函控制/差异调节/替代程序，而点开渲染的却是三张发函记录表
（渲染按 `workpaper_sheet_classification` 的 `wp_code` 行解析，那张表是对的）
→ 审计师在导航里找不到发函记录表。

## 范围外（留 spec `e0-confirmation-completion`）

1. **补 E0A / E0-6 / E0-7 / E0-8 四条缺失映射** —— 缺映射 ⇒ `matched_codes` 不含它们
   ⇒ 这四张永远不会生成独立 `wp_index`（只能从 wp_code=E0 整册进入）。补映射必须同时补
   `wp_code_overrides`，否则 `test_e_class_override_count_matches_mapping` 立刻红。
2. **`account_codes` 仍为 `['1002']`** —— E0-4 借款/E0-5 应付票据的账户其实是 2001/2501/2201。
   改它会改变 `matched_codes` ⇒ 改变项目脚手架，属独立变更。
3. **存量 `wp_index` 行不自愈** —— 本脚本只修种子；已建项目（实测 2 个）的旧名需另做
   幂等 UPDATE（写库，须显式确认）。

用法（cwd=backend）：
    python scripts/fix/fix_e0_wp_account_mapping.py --check
    python scripts/fix/fix_e0_wp_account_mapping.py --dry-run
    python scripts/fix/fix_e0_wp_account_mapping.py --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_MAPPING = Path(__file__).resolve().parents[2] / "data" / "wp_account_mapping.json"

# 逐字取自源模板 `E0 货币资金 - 函证（Leap应对措施-函证）.xlsx` 的 `底稿目录` E 列
# （行 8 = 序号 6 = 索引号 E0-5 = 应付银行承兑汇票发函记录表）。
E0_EXPECTED: dict[str, dict[str, str]] = {
    "E0-3": {"wp_name": "货币资金发函记录表", "account_name": "货币资金发函"},
    "E0-4": {"wp_name": "借款发函记录表", "account_name": "借款发函"},
    "E0-5": {"wp_name": "应付银行承兑汇票发函记录表", "account_name": "应付票据发函"},
}

# 已知欠账：源模板 `底稿目录` 有、本文件缺的映射（补齐属 spec 范围，见模块 docstring）
E0_KNOWN_MISSING: dict[str, str] = {
    "E0A": "函证程序表",
    "E0-6": "理财产品发函记录表",
    "E0-7": "跟函函证过程控制",
    "E0-8": "函证程序舞弊风险评价表",
}


def _load() -> dict:
    with open(_MAPPING, encoding="utf-8-sig") as f:
        return json.load(f)


def plan(data: dict) -> list[tuple[str, str, str, str]]:
    """返回 [(wp_code, field, old, new)]，空 = 无欠账。"""
    changes: list[tuple[str, str, str, str]] = []
    for entry in data.get("mappings", []):
        code = entry.get("wp_code")
        want = E0_EXPECTED.get(code)
        if not want:
            continue
        for field, new in want.items():
            old = entry.get(field) or ""
            if old != new:
                changes.append((code, field, old, new))
    return changes


def apply_plan(data: dict) -> int:
    n = 0
    for entry in data.get("mappings", []):
        want = E0_EXPECTED.get(entry.get("wp_code"))
        if not want:
            continue
        for field, new in want.items():
            if entry.get(field) != new:
                entry[field] = new
                n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="只报欠账，有欠账 exit 1")
    g.add_argument("--dry-run", action="store_true", help="打印将要做的变更，不写盘")
    g.add_argument("--apply", action="store_true", help="写盘")
    args = ap.parse_args()

    raw = _MAPPING.read_text(encoding="utf-8-sig")
    data = json.loads(raw)
    changes = plan(data)

    for code, field, old, new in changes:
        print(f"  [{code}] {field}: {old!r} -> {new!r}")
    missing = [c for c in E0_KNOWN_MISSING if not any(
        e.get("wp_code") == c for e in data.get("mappings", []))]
    if missing:
        print(f"  [info] 源模板底稿目录有、本文件缺的映射（属 spec 范围）: {missing}")

    if args.check:
        if changes:
            print(f"[fix_e0_wp_account_mapping] {len(changes)} 项欠账")
            return 1
        print("[fix_e0_wp_account_mapping] 0 项欠账")
        return 0

    if not changes:
        print("[fix_e0_wp_account_mapping] 已是目标状态，空操作")
        return 0

    if args.dry_run or not args.apply:
        print(f"[fix_e0_wp_account_mapping] dry-run：{len(changes)} 项待改（加 --apply 写盘）")
        return 0

    n = apply_plan(data)
    # round-trip 自检：除目标字段外不得有任何其它差异（防全文件重排 / 并发覆盖）
    before = json.loads(raw)
    apply_plan(before)
    if json.dumps(before, ensure_ascii=False, sort_keys=True) != json.dumps(
        data, ensure_ascii=False, sort_keys=True
    ):
        print("[fix_e0_wp_account_mapping] round-trip 自检失败，未写盘")
        return 2
    _MAPPING.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[fix_e0_wp_account_mapping] 已写入 {n} 项 -> {_MAPPING}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
