#!/usr/bin/env python
"""check_review_prompt_coverage.py — CI 守卫：覆盖率 + 结构校验

用法: python scripts/check/check_review_prompt_coverage.py [--strict]

检查 D/ 目录下的提示词覆盖率，并校验每个文件包含 tips / checklist / risk_areas，
checklist 条目数达到最低门槛。
--strict 模式下不达标则 exit 1（用于 CI）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "data" / "tsj_review_prompts"

EXPECTED_D2_SHEETS = {
    "D2-1", "D2-2", "D2-3", "D2-4", "D2-5", "D2-6", "D2-7", "D2-8",
    "D2-9", "D2-10", "D2-11", "D2-12", "D2-13",
    "D2-cutoff",
    "D2-note-listed", "D2-note-soe",
}

REQUIRED_SECTIONS = ("tips", "checklist", "risk_areas")
MIN_CHECKLIST_ITEMS = 8

_SECTION_RE = re.compile(r"^##\s+(\w+)\s*$", re.MULTILINE)
_CHECKLIST_ITEM_RE = re.compile(r"^-\s*\[[ xX]?\]\s+", re.MULTILINE)


def _validate_structure(path: Path) -> list[str]:
    """返回结构问题列表；空列表表示通过。"""
    issues: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return [f"无法读取: {e}"]

    sections = {m.group(1).lower() for m in _SECTION_RE.finditer(text)}
    for req in REQUIRED_SECTIONS:
        if req not in sections:
            issues.append(f"缺少 ## {req} 段落")

    checklist_count = len(_CHECKLIST_ITEM_RE.findall(text))
    if checklist_count < MIN_CHECKLIST_ITEMS:
        issues.append(
            f"checklist 条目不足（{checklist_count} < {MIN_CHECKLIST_ITEMS}）"
        )

    if not text.strip().startswith("---"):
        issues.append("缺少 YAML front-matter")

    return issues


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

    structure_failures: list[str] = []
    for stem in sorted(EXPECTED_D2_SHEETS & existing):
        path = d_dir / f"{stem}.md"
        issues = _validate_structure(path)
        if issues:
            structure_failures.append(f"{stem}: {'; '.join(issues)}")
            print(f"[WARN] 结构问题 {stem}: {'; '.join(issues)}")
        else:
            print(f"[OK] 结构通过: {stem}")

    failed = bool(missing) or bool(structure_failures)

    if failed and strict:
        print(
            f"[FAIL] --strict 模式阻断: missing={len(missing)}, "
            f"structure={len(structure_failures)}"
        )
        return 1

    if failed:
        print("[WARN] 覆盖率/结构有问题（非 strict，不阻断）")
        return 0

    print("[OK] 覆盖率与结构检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
