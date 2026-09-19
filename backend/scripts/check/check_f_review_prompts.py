#!/usr/bin/env python3
"""Lint F-cycle sheet-level review prompts under tsj_review_prompts/F/."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
F_DIR = ROOT / "data" / "tsj_review_prompts" / "F"

REQUIRED_SECTIONS = ("## tips", "## checklist", "## risk_areas")
MIN_CHECKBOX = 5


def main() -> int:
    if not F_DIR.is_dir():
        print("[FAIL] F/ directory missing")
        return 1
    files = sorted(F_DIR.glob("F*.md"))
    if len(files) < 80:
        print(f"[FAIL] expected >=80 F*.md, got {len(files)}")
        return 1
    fails = 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        for sec in REQUIRED_SECTIONS:
            if sec not in text:
                print(f"[FAIL] {path.name}: missing {sec}")
                fails += 1
        boxes = len(re.findall(r"^- \[ \]", text, re.M))
        if boxes < MIN_CHECKBOX:
            print(f"[FAIL] {path.name}: checklist items {boxes} < {MIN_CHECKBOX}")
            fails += 1
        # reserved ghosts must not exist as prompts
        if path.stem in {
            "F2-15", "F2-17", "F2-27", "F2-28",
            "F2-36", "F2-37", "F2-45", "F2-46", "F2-50", "F2-51",
        }:
            print(f"[FAIL] reserved sheet should not have prompt: {path.name}")
            fails += 1
    # subject coverage
    for prefix in ("F1", "F2", "F3", "F4", "F5"):
        n = sum(1 for f in files if f.stem == prefix or f.stem.startswith(prefix + "-") or f.stem.startswith(prefix + "A"))
        if n < 5:
            print(f"[FAIL] {prefix} coverage too low: {n}")
            fails += 1
        else:
            print(f"[PASS] {prefix} files={n}")
    if fails:
        print(f"[FAIL] {fails} issues")
        return 1
    print(f"[PASS] {len(files)} F-cycle prompts OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
