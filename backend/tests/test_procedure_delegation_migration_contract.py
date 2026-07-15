"""Migration reservation contract for procedure delegation.

Task 2 landed the canonical V105 feature migration; the migration head advances
to 105. This contract now locks the post-Task-2 truth: V105 exists as the single
canonical file and matches the architecture guard's constants.
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


def test_v105_is_highest_and_only_canonical_variant_exists():
    migrations = _versioned_migrations()
    assert migrations, "expected existing versioned migrations"
    assert migrations[-1][0] == CURRENT_MIGRATION_VERSION
    assert CURRENT_MIGRATION_VERSION == 105
    assert migrations[-1][1].name == CANONICAL_V105_FILENAME

    # canonical V105 present and no duplicate/misnamed variant (runner dedup safety)
    v105 = sorted(p.name for p in MIGRATION_DIR.glob("V105*.sql"))
    assert v105 == [CANONICAL_V105_FILENAME]
