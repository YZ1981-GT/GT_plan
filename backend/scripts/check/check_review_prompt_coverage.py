#!/usr/bin/env python
"""check_review_prompt_coverage.py — CI 守卫：新增科目底稿必须有对应提示词文件

用法: python scripts/check/check_review_prompt_coverage.py [--strict]

检查 D/ 目录下的提示词覆盖率，确保所有已知 D2 sheet 都有提示词文件。
--strict 模式下覆盖率不达标则 exit 1（用于 CI）。
"""
from __future__ import annotations

import sys
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "data" / "tsj_review_prompts"

# 预期的 D2 底稿列表（与 GtD2AccountsReceivable.vue 的 KNOWN_HTML_SHEETS 对应）
EXPECTED_D2_SHEETS = {
    "D2-1", "D2-2", "D2-3", "D2-4", "D2-5", "D2-6", "D2-7", "D2-8",
    "D2-note-listed", "D2-note-soe",
}


def main() -> int:
    strict = "--strict" in sys.argv

    d_dir = PROMPTS_DIR / "D"
    if not d_dir.is_dir():
        print(f"[ERROR] D/ 目录不存在: {d_dir}")
        return 1 if strict else 0

    existing = {f.stem for f in d_dir.glob("*.md")}

    missing = EXPECTED_D2_SHEETS - existing
    extra = existing - EXPECTED_D2_SHEETS

    print(f"[INFO] D2 提示词覆盖率: {len(existing & EXPECTED_D2_SHEETS)}/{len(EXPECTED_D2_SHEETS)}")
    print(f"[INFO] 预期文件: {sorted(EXPECTED_D2_SHEETS)}")
    print(f"[INFO] 已有文件: {sorted(existing)}")

    if missing:
        print(f"[WARN] 缺失提示词文件: {sorted(missing)}")
    if extra:
        print(f"[INFO] 额外提示词文件（非预期但不阻断）: {sorted(extra)}")

    if missing and strict:
        print(f"[FAIL] --strict 模式下有 {len(missing)} 个缺失文件，CI 阻断")
        return 1

    print("[OK] 覆盖率检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
