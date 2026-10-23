#!/usr/bin/env python3
"""hi-cycle-four-table-extraction 契约守卫（Task 5.2）.

校验 H5-I6 Tier A 预设的锚点 ⊆ anchor_registry 且表达式仅含 TB/SUM_TB/ABS。
挂 governance-checks.yml (--strict 退出非0阻断)。

没有标准科目、预设被删掉的底稿（I5 其他非流动资产）在预设库里留 ``_{wp_code}_removed`` 声明：
必须写明 ``_why`` / ``_anchor`` / ``_spec``，且该锚点确实既无预设也无推送规则（声明可被现状证伪，
不是加一行就放行的后门）。spec: formula-fetch-and-wp-generation-defect-closure R1.3。

用法:
    python backend/scripts/check/check_hi_extraction_presets_contract.py [--strict]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PRESETS_PATH = ROOT / "backend" / "data" / "d_cycle_extraction" / "d_cycle_extraction_presets.json"
REGISTRY_PATH = ROOT / "backend" / "data" / "d_cycle_extraction" / "d_cycle_anchor_registry.json"
RULES_PATH = ROOT / "backend" / "data" / "formula_push_rules.json"

# H/I wp_codes 范围
HI_CODES = {"H5", "H6", "H7", "H8", "H9", "H10", "I1", "I2", "I3", "I4", "I5", "I6"}

# 允许的公式函数（Tier A 只用 TB/SUM_TB/ABS，不含 AUX/PREV/序时账）
_ALLOWED_FUNC_RE = re.compile(r"^(TB|SUM_TB|ABS)\s*\(", re.IGNORECASE)
_FUNC_RE = re.compile(r"([A-Z_]+)\s*\(", re.IGNORECASE)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _check_removed(wp_code: str, decl: object, entries: list, rule_items: set[str], errors: list[str]) -> None:
    """``_{wp_code}_removed`` 声明：字段齐全，且与现状一致（没有预设、没有该锚点的推送规则）。"""
    if not isinstance(decl, dict):
        errors.append(f"{wp_code}: 移除声明必须是对象")
        return
    missing = [k for k in ("_why", "_anchor", "_spec") if not str(decl.get(k) or "").strip()]
    if missing:
        errors.append(f"{wp_code}: 移除声明缺少 {missing}")
    if entries:
        errors.append(f"{wp_code}: 已声明移除却仍有 {len(entries)} 条预设")
    anchor = str(decl.get("_anchor") or "").strip()
    if anchor and anchor in rule_items:
        errors.append(f"{wp_code}: 已声明移除的锚点 '{anchor}' 仍有推送规则")


def main() -> int:
    strict = "--strict" in sys.argv
    errors: list[str] = []

    presets = _load_json(PRESETS_PATH)
    registry = _load_json(REGISTRY_PATH)
    rules = _load_json(RULES_PATH).get("rules") or []
    rule_items = {str((r.get("target") or {}).get("item_id") or "") for r in rules} - {""}

    removed_codes = 0
    for wp_code in sorted(HI_CODES):
        entries = presets.get(wp_code, [])
        decl_key = f"_{wp_code}_removed"
        if decl_key in presets:
            _check_removed(wp_code, presets[decl_key], entries, rule_items, errors)
            removed_codes += 1
            continue
        if not entries:
            errors.append(f"{wp_code}: 预设库无条目（没有标准科目时须留 {decl_key} 声明）")
            continue

        # 获取该 wp_code 的锚点集
        anchors_raw = registry.get(wp_code, [])
        exact_anchors = {a for a in anchors_raw if isinstance(a, str) and not a.startswith("re:")}
        pattern_anchors = []
        for a in anchors_raw:
            if isinstance(a, str) and a.startswith("re:"):
                try:
                    pattern_anchors.append(re.compile(a[3:]))
                except re.error:
                    pass

        def is_known(anchor: str) -> bool:
            if anchor in exact_anchors:
                return True
            return any(p.match(anchor) for p in pattern_anchors)

        for entry in entries:
            anchor = entry.get("anchor", "")
            expression = entry.get("expression", "")

            # 校验1: anchor ∈ registry
            if not is_known(anchor):
                errors.append(f"{wp_code}: 锚点 '{anchor}' 不在 anchor_registry")

            # 校验2: 表达式仅含允许的函数
            funcs_in_expr = _FUNC_RE.findall(expression)
            for func in funcs_in_expr:
                if not _ALLOWED_FUNC_RE.match(f"{func}("):
                    errors.append(f"{wp_code}: 表达式含不支持函数 '{func}' in '{expression}'")

    # 报告
    total_presets = sum(len(presets.get(c, [])) for c in HI_CODES)
    print(f"[hi-extraction-presets-contract] {len(HI_CODES)} wp_codes, {total_presets} presets, "
          f"{removed_codes} removed, {len(errors)} errors")

    if errors:
        for e in errors:
            print(f"  ERROR: {e}")
        if strict:
            return 1
    else:
        print("  All checks passed.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
