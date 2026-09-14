#!/usr/bin/env python3
"""One-time migration of coverage-ledger.json to capability-level schema v2.

Legacy entry exemptions are assigned to one capability only when their reason
is unambiguous.  Ambiguous exemptions are reported and are not carried over.
The command is idempotent and writes atomically.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent
CHECK_DIR = SCRIPT_DIR.parent / "check"
sys.path.insert(0, str(CHECK_DIR))

from capability_ledger import (  # noqa: E402
    CAPABILITIES,
    RUNTIME_CAPABILITIES,
    capability_record,
    normalize_ledger,
)
from generate_coverage_ledger import (  # noqa: E402
    component_type_for,
    detect_capabilities,
    detect_shell_evidence,
    find_main_entry_files,
    load_wp_code_overrides,
)

DEFAULT_LEDGER = (
    PROJECT_ROOT / "audit-platform" / "frontend" / "src"
    / "components" / "workpaper" / "coverage-ledger.json"
)


def enrich_with_current_evidence(ledger: dict, overrides: dict) -> dict:
    """Add entry metadata and replace legacy markers with current source evidence."""
    entry_files = find_main_entry_files()
    for wp_code, entry in ledger.get("entries", {}).items():
        entry_file = entry_files.get(wp_code)
        entry["componentType"] = component_type_for(wp_code, overrides)
        if entry_file is None:
            entry.setdefault("entryFile", None)
            continue
        entry["entryFile"] = entry_file.relative_to(PROJECT_ROOT).as_posix()
        detected = detect_capabilities(entry_file)
        shell_evidence = detect_shell_evidence(entry_file)
        records = entry["capabilities"]
        for capability in CAPABILITIES:
            current_evidence = list(detected[capability])
            if shell_evidence and capability in RUNTIME_CAPABILITIES:
                current_evidence.extend(shell_evidence)
            record = records[capability]
            if current_evidence and record["status"] != "exempt":
                records[capability] = capability_record(
                    "covered", current_evidence
                )
    return ledger


def migrate_file(input_path: Path, output_path: Path, dry_run: bool = False) -> list[str]:
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    migrated, warnings = normalize_ledger(raw)
    migrated = enrich_with_current_evidence(migrated, load_wp_code_overrides())
    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_suffix(output_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(migrated, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(output_path)
    return warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate Capability Ledger to schema v2")
    parser.add_argument("--input", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    output = args.output or args.input
    try:
        warnings = migrate_file(args.input, output, args.dry_run)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"[FAIL] Capability Ledger migration: {exc}", file=sys.stderr)
        return 1

    action = "validated" if args.dry_run else f"written to {output}"
    print(f"[OK] Capability Ledger schema v2 {action}")
    for warning in warnings:
        print(f"[WARN] {warning}")
    if warnings:
        print("[WARN] Ambiguous legacy exemptions were not migrated as exemptions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
