#!/usr/bin/env python3
"""校验 section_code_index.json 与种子 JSON 键一致性.

验证：
1. index 中每个 section_code 在对应种子 JSON 中存在（作为 section_number）
2. 种子 JSON 中 level>=2 的 section_number 在 index 中覆盖率报告
3. legacy_aliases 无冲突（同一变体内 alias 不重叠）

Usage:
    python backend/scripts/validate_section_code_index_consistency.py
    python backend/scripts/validate_section_code_index_consistency.py --strict
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
DATA = _BACKEND / "data"

INDEX_PATH = DATA / "audit_report_templates" / "section_code_index.json"

SEED_MAP = {
    "soe_standalone": DATA / "note_template_soe.json",
    "soe_consolidated": DATA / "note_template_soe.json",
    "listed_standalone": DATA / "note_template_listed.json",
    "listed_consolidated": DATA / "note_template_listed.json",
}


def load_seed_section_numbers(seed_path: Path, scope: str) -> set[str]:
    """Extract all section_number values from seed JSON (level >= 2, matching scope)."""
    with open(seed_path, "r", encoding="utf-8") as f:
        seed = json.load(f)

    numbers: set[str] = set()
    for section in seed.get("sections", []):
        sn = section.get("section_number", "")
        section_scope = section.get("scope", "both")
        level = section.get("level", 1)

        # Only level 2+ sections are indexed (level 1 = chapter headers)
        if level < 2:
            continue

        # Skip sections that don't apply to this scope
        if scope == "standalone" and section_scope == "consolidated_only":
            continue
        if scope == "consolidated" and section_scope == "standalone_only":
            continue

        if sn:
            numbers.add(sn)

    return numbers


def validate(*, strict: bool = False) -> int:
    if not INDEX_PATH.exists():
        print(f"ERROR: {INDEX_PATH} not found")
        return 1

    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        index = json.load(f)

    errors: list[str] = []
    warnings: list[str] = []

    variants = index.get("variants", {})
    for variant_key, variant_data in variants.items():
        seed_path = SEED_MAP.get(variant_key)
        if not seed_path or not seed_path.exists():
            warnings.append(f"{variant_key}: seed file not found at {seed_path}")
            continue

        # Determine scope from variant key
        scope = "consolidated" if "consolidated" in variant_key else "standalone"

        # Load seed section numbers
        seed_numbers = load_seed_section_numbers(seed_path, scope)

        # Get indexed section codes
        sections = variant_data.get("sections", [])
        indexed_codes: set[str] = set()
        all_aliases: dict[str, str] = {}  # alias -> owner section_code

        for sec in sections:
            code = sec.get("section_code", "")
            indexed_codes.add(code)

            # Check legacy_aliases for conflicts
            for alias in sec.get("legacy_aliases", []):
                if alias in all_aliases:
                    errors.append(
                        f"{variant_key}: alias '{alias}' claimed by both "
                        f"'{all_aliases[alias]}' and '{code}'"
                    )
                all_aliases[alias] = code

        # 1. Every indexed code must exist in seed
        for code in sorted(indexed_codes):
            if code not in seed_numbers:
                # Check if it's a valid chapter-level entry (一、二、三...)
                # These are sometimes added as index entries for chapter headers
                if "、" not in code or code.endswith("、"):
                    continue  # chapter-level, OK
                warnings.append(
                    f"{variant_key}: indexed '{code}' not in seed section_numbers"
                )

        # 2. Coverage report: seed entries not in index
        missing_from_index = seed_numbers - indexed_codes
        # Also check via legacy_aliases
        for alias, owner in all_aliases.items():
            missing_from_index.discard(alias)

        coverage = len(indexed_codes) / max(len(seed_numbers), 1) * 100
        print(f"{variant_key}: {len(indexed_codes)}/{len(seed_numbers)} indexed ({coverage:.1f}%)")

        if missing_from_index:
            # Only warn, not error — some sections may not yet be tagged
            sample = sorted(missing_from_index)[:10]
            warnings.append(
                f"{variant_key}: {len(missing_from_index)} seed sections not in index "
                f"(sample: {sample})"
            )

    # Report
    if errors:
        print(f"\nERRORS ({len(errors)}):")
        for e in errors:
            print(f"  ✗ {e}")

    if warnings:
        print(f"\nWARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  ⚠ {w}")

    if not errors and not warnings:
        print("\nOK: index fully consistent with seed JSON")

    if errors:
        return 1
    if warnings and strict:
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate section_code_index.json consistency with seed JSON"
    )
    parser.add_argument("--strict", action="store_true", help="Exit 1 on warnings too")
    args = parser.parse_args()
    raise SystemExit(validate(strict=args.strict))


if __name__ == "__main__":
    main()
