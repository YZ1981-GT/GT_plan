#!/usr/bin/env python3
"""校验附注 Word 模板：拒绝【、使用说明、XXXX 等编制残留.

Usage:
    python backend/scripts/validate_note_template.py
    python backend/scripts/validate_note_template.py --variant soe_standalone
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from docx import Document

_BACKEND = Path(__file__).resolve().parent.parent
DATA = _BACKEND / "data"
NOTES_DIR = DATA / "audit_report_templates" / "disclosure_notes"

FORBIDDEN_PATTERNS = [
    (re.compile(r"【"), "【"),
    (re.compile(r"使用说明"), "使用说明"),
    (re.compile(r"XXXX"), "XXXX"),
]

VARIANT_FILES = {
    "soe_standalone": "soe_standalone.docx",
    "soe_consolidated": "soe_consolidated.docx",
    "listed_standalone": "listed_standalone.docx",
    "listed_consolidated": "listed_consolidated.docx",
}


def scan_docx(path: Path) -> list[str]:
    issues: list[str] = []
    doc = Document(path)
    for i, para in enumerate(doc.paragraphs):
        text = (para.text or "").strip()
        if not text:
            continue
        for pattern, label in FORBIDDEN_PATTERNS:
            if pattern.search(text):
                issues.append(f"para[{i}] forbidden '{label}': {text[:80]}")
    return issues


def validate_variants(variants: list[str] | None = None) -> int:
    targets = variants or list(VARIANT_FILES.keys())
    exit_code = 0
    for key in targets:
        fname = VARIANT_FILES.get(key)
        if not fname:
            print(f"UNKNOWN variant: {key}")
            exit_code = 1
            continue
        path = NOTES_DIR / fname
        if not path.is_file():
            print(f"MISSING: {path}")
            exit_code = 1
            continue
        issues = scan_docx(path)
        if issues:
            print(f"FAIL {key} ({len(issues)} issues):")
            for item in issues[:20]:
                print(f"  - {item}")
            if len(issues) > 20:
                print(f"  ... +{len(issues) - 20} more")
            exit_code = 1
        else:
            print(f"OK {key}")
    return exit_code


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate disclosure note Word templates")
    parser.add_argument(
        "--variant",
        action="append",
        dest="variants",
        help="Variant key (repeatable); default all four",
    )
    args = parser.parse_args()
    raise SystemExit(validate_variants(args.variants))


if __name__ == "__main__":
    main()
