"""
Seed file schema validation script.

Loads each seed JSON file in backend/data/ and validates against
its corresponding Pydantic schema defined in backend/data/_seed_schemas.py.

Usage:
    python scripts/validate_seed_files.py

Exit codes:
    0 — all seed files valid
    1 — one or more validation failures
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Resolve paths relative to project root (script lives in scripts/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "backend" / "data"

# Add project root to sys.path so we can import backend.data._seed_schemas
sys.path.insert(0, str(PROJECT_ROOT))

from backend.data._seed_schemas import (  # noqa: E402
    AuditLogRuleEntry,
    AuditReportTemplatesSeed,
    IndependenceQuestion,
    NoteTemplatesSeed,
    QcRuleDefinitionEntry,
    ReportConfig,
    WpAccountMappingSeed,
)
from pydantic import TypeAdapter, ValidationError  # noqa: E402


# ─── Seed file registry ─────────────────────────────────────────────────────

SEED_FILES: list[dict[str, Any]] = [
    {
        "filename": "audit_report_templates_seed.json",
        "validator": lambda data: AuditReportTemplatesSeed.model_validate(data),
        "required": True,
    },
    {
        "filename": "report_config_seed.json",
        "validator": lambda data: TypeAdapter(list[ReportConfig]).validate_python(data),
        "required": True,
    },
    {
        "filename": "note_templates_seed.json",
        "validator": lambda data: NoteTemplatesSeed.model_validate(data),
        "required": True,
    },
    {
        "filename": "wp_account_mapping.json",
        "validator": lambda data: WpAccountMappingSeed.model_validate(data),
        "required": True,
    },
    {
        "filename": "independence_questions_annual.json",
        "validator": lambda data: TypeAdapter(list[IndependenceQuestion]).validate_python(data),
        "required": True,
    },
    {
        "filename": "qc_rule_definitions_seed.json",
        "validator": lambda data: TypeAdapter(list[QcRuleDefinitionEntry]).validate_python(data),
        "required": True,
    },
    {
        "filename": "audit_log_rules_seed.json",
        "validator": lambda data: TypeAdapter(list[AuditLogRuleEntry]).validate_python(data),
        "required": False,
    },
]


# ─── Main ────────────────────────────────────────────────────────────────────


def validate_seed_files() -> bool:
    """Validate all registered seed files. Returns True if all pass."""
    all_passed = True
    total = 0
    passed = 0
    skipped = 0

    for entry in SEED_FILES:
        filename = entry["filename"]
        filepath = DATA_DIR / filename
        required = entry["required"]

        if not filepath.exists():
            if required:
                print(f"  FAIL  {filename} — file not found (required)")
                all_passed = False
                total += 1
            else:
                print(f"  SKIP  {filename} — file not found (optional)")
                skipped += 1
            continue

        total += 1

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"  FAIL  {filename} — invalid JSON: {e}")
            all_passed = False
            continue

        try:
            entry["validator"](data)
            print(f"  PASS  {filename}")
            passed += 1
        except ValidationError as e:
            print(f"  FAIL  {filename} — schema validation failed:")
            # Show first 5 errors to keep output readable
            for err in e.errors()[:5]:
                loc = " -> ".join(str(x) for x in err["loc"])
                print(f"         [{loc}] {err['msg']}")
            if len(e.errors()) > 5:
                print(f"         ... and {len(e.errors()) - 5} more errors")
            all_passed = False

    print()
    print(f"Results: {passed}/{total} passed, {skipped} skipped")
    return all_passed


def main() -> None:
    print("=" * 60)
    print("Seed File Schema Validation")
    print("=" * 60)
    print()

    success = validate_seed_files()

    if success:
        print("\nAll seed files validated successfully.")
        sys.exit(0)
    else:
        print("\nSeed validation FAILED. See errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
