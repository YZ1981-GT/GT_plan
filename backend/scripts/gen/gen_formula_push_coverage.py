#!/usr/bin/env python
"""生成公式推送接入等级清册。

输出 `backend/data/formula_push_coverage.json`：只放结构事实（等级、规则数、独占键数）。
幂等（无时间戳）；`--check` 漂移 exit 2。

spec: formula-push-all-subjects-rollout · Task 21 · 需求 6.1~6.3
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = ROOT / "data" / "formula_push_rules.json"
OUTPUT_PATH = ROOT / "data" / "formula_push_coverage.json"

# 确保 backend/ 在 sys.path（脚本直接运行时需要）
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def compute_coverage(rules_path: Path = RULES_PATH) -> dict:
    """从规则清单 + 注册表计算接入等级清册。"""
    from app.services.formula_push.bindings import supported_wp_codes, get_binding
    from app.services.formula_push.owned_keys import owned_item_ids

    document = json.loads(rules_path.read_text("utf-8"))
    rules = document.get("rules") or []

    # 按主编码统计规则
    rule_counts: dict[str, int] = {}
    for rule in rules:
        wp_code = (rule.get("page_key") or "").split(":", 1)[-1]
        rule_counts[wp_code] = rule_counts.get(wp_code, 0) + 1

    codes = sorted(supported_wp_codes())
    entries = []
    for code in codes:
        binding = get_binding(code)
        owned = owned_item_ids(code, rules_path=rules_path)
        entries.append({
            "wp_code": code,
            "level": "L3",
            "account_prefixes": list(binding.account_prefixes),
            "rule_count": rule_counts.get(code, 0),
            "owned_key_count": len(owned),
            "has_note_rules": any(
                r.get("target", {}).get("domain") == "note"
                and (r.get("page_key") or "").endswith(f":{code}")
                for r in rules
            ),
        })

    return {
        "version": 1,
        "registered_codes": codes,
        "entries": entries,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="生成公式推送接入等级清册")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    coverage = compute_coverage()
    content = json.dumps(coverage, ensure_ascii=False, indent=2) + "\n"

    if args.check:
        if not OUTPUT_PATH.exists():
            print("清册文件不存在", file=sys.stderr)
            sys.exit(2)
        existing = OUTPUT_PATH.read_text("utf-8")
        if existing == content:
            print(f"清册文件与注册表一致（{len(coverage['entries'])} 条）")
            sys.exit(0)
        print("清册文件与注册表不一致", file=sys.stderr)
        sys.exit(2)

    OUTPUT_PATH.write_text(content, encoding="utf-8")
    print(f"已生成 {OUTPUT_PATH}（{len(coverage['entries'])} 条）")


if __name__ == "__main__":
    main()
