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
    import re
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

    # ── 不适用码登记 ──────────────────────────────────────────────────────
    mapping_path = ROOT / "data" / "wp_account_mapping.json"
    mapping_raw = json.loads(mapping_path.read_text("utf-8"))
    primary_re = re.compile(r"^[A-Z]\d+$")
    all_primary: dict[str, dict] = {}
    for item in mapping_raw.get("mappings", []):
        c = item.get("wp_code", "")
        if primary_re.fullmatch(c) and c not in all_primary:
            all_primary[c] = item

    registered_set = set(codes)
    not_applicable: list[dict] = []
    for code in sorted(set(all_primary) - registered_set):
        item = all_primary[code]
        accts = item.get("account_codes", [])
        name = item.get("account_name", "")
        cycle = code[0]
        # 分类判定
        if cycle == "A":
            reason = "A 循环（报表/调整/沟通类）：文档型底稿，无科目余额取数需求"
        elif cycle == "B":
            reason = "B 循环（计划/控制了解）：审计计划与风险评估类底稿，无数值计算"
        elif cycle == "C":
            reason = "C 循环（控制测试）：控制测试检查表/评价表，纯流程类底稿"
        elif code.endswith("0") and accts and cycle in "DEFGHKL":
            reason = f"函证中心底稿（{name}），数据来自询证程序结果而非试算表公式推送"
        elif cycle == "S" and not accts:
            reason = f"S 循环专项考虑（{name or code}），无科目码关联，文档/分析类底稿"
        elif cycle == "S" and accts:
            reason = f"S 循环专项（{name}），有前端 FormulaEngine 但不需要后端推送"
        elif accts:
            reason = f"有科目码（{','.join(accts)}），后续可接入候选"
        else:
            reason = f"无科目码关联（{name or code}），文档/管理类底稿"
        not_applicable.append({
            "wp_code": code,
            "reason": reason,
            "account_codes": accts,
        })

    return {
        "version": 2,
        "registered_codes": codes,
        "entries": entries,
        "not_applicable": not_applicable,
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
    print(f"已生成 {OUTPUT_PATH}（{len(coverage['entries'])} 条已注册 + {len(coverage.get('not_applicable', []))} 条不适用）")


if __name__ == "__main__":
    main()
