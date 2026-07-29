#!/usr/bin/env python3
"""hi-cycle-four-table-extraction 契约守卫（Task 5.2）.

校验 H5-I6 Tier A 预设的锚点 ⊆ anchor_registry 且表达式仅含 TB/SUM_TB/ABS。
挂 governance-checks.yml (--strict 退出非0阻断)。

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

# H/I wp_codes 范围
HI_CODES = {"H5", "H6", "H7", "H8", "H9", "H10", "I1", "I2", "I3", "I4", "I5", "I6"}

# 允许的公式函数（Tier A 只用 TB/SUM_TB/ABS，不含 AUX/PREV/序时账）
_ALLOWED_FUNC_RE = re.compile(r"^(TB|SUM_TB|ABS)\s*\(", re.IGNORECASE)
_FUNC_RE = re.compile(r"([A-Z_]+)\s*\(", re.IGNORECASE)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    strict = "--strict" in sys.argv
    errors: list[str] = []

    presets = _load_json(PRESETS_PATH)
    registry = _load_json(REGISTRY_PATH)

    for wp_code in HI_CODES:
        entries = presets.get(wp_code, [])
        if not entries:
            errors.append(f"{wp_code}: 预设库无条目")
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
    print(f"[hi-extraction-presets-contract] {len(HI_CODES)} wp_codes, {total_presets} presets, {len(errors)} errors")

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
