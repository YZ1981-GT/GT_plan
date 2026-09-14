"""Migration reservation contract for procedure delegation.

Task 2 landed the canonical V105 feature migration. Later features may add
higher-numbered migrations (e.g. evidence-governance V106–V109); this contract
locks that V105 remains the single canonical procedure_row_tasks file.
"""
from __future__ import annotations

import re
from pathlib import Path

MIGRATION_DIR = Path(__file__).resolve().parents[1] / "migrations"
try:
    from scripts.check.check_procedure_delegation_architecture import (
        CANONICAL_V105_FILENAME,
        CURRENT_MIGRATION_VERSION,
    )
except ImportError:  # governance script must exist post-Task-1; fallback mirrors它.
    CURRENT_MIGRATION_VERSION = 105
    CANONICAL_V105_FILENAME = "V105__procedure_row_tasks.sql"
_VERSIONED_MIGRATION = re.compile(r"^V(?P<version>\d{3})__.+\.sql$")


def _versioned_migrations() -> list[tuple[int, Path]]:
    found = []
    for path in MIGRATION_DIR.glob("V*.sql"):
        match = _VERSIONED_MIGRATION.fullmatch(path.name)
        if match:
            found.append((int(match.group("version")), path))
    return sorted(found)


def test_v105_is_canonical_and_only_variant_exists():
    migrations = _versioned_migrations()
    assert migrations, "expected existing versioned migrations"
    v105_entries = [m for m in migrations if m[0] == CURRENT_MIGRATION_VERSION]
    assert len(v105_entries) == 1, f"expected exactly one V{CURRENT_MIGRATION_VERSION:03d} migration"
    assert v105_entries[0][1].name == CANONICAL_V105_FILENAME
    assert CURRENT_MIGRATION_VERSION == 105

    # canonical V105 present and no duplicate/misnamed variant (runner dedup safety)
    v105 = sorted(p.name for p in MIGRATION_DIR.glob("V105*.sql"))
    assert v105 == [CANONICAL_V105_FILENAME]
