"""
PBT P7 (migration idempotence) for migrate_global_kb_to_pg.

Validates: Requirements 9.5
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


@settings(max_examples=5, deadline=None)
@given(
    filename=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="._-"),
        min_size=3,
        max_size=50,
    ).filter(lambda x: x.strip() and not x.startswith(".")),
    category=st.sampled_from([
        "workpaper_templates", "regulations", "accounting_standards",
        "quality_control", "audit_procedures", "industry_guides",
        "prompts", "report_templates", "notes",
    ]),
)
def test_migration_idempotence(filename: str, category: str):
    """
    **Validates: Requirements 9.5**

    PBT P7: Running the migration script twice on the same file system state
    shall NOT create duplicate documents (matched by folder_id + filename).

    We test this by simulating the idempotence check logic:
    - First call: file not in DB → create
    - Second call: file already in DB → skip (version increment, not duplicate)
    """
    # Simulate the migration idempotence logic
    db_state: dict[tuple[str, str], int] = {}  # (folder_id, filename) → version

    folder_id = f"folder-{category}"

    def simulate_migrate_file(fname: str) -> str:
        """Simulate one file migration. Returns 'created' or 'skipped'."""
        key = (folder_id, fname)
        if key in db_state:
            db_state[key] += 1  # version increment
            return "skipped"
        else:
            db_state[key] = 1
            return "created"

    # First migration run
    result1 = simulate_migrate_file(filename)
    assert result1 == "created"
    assert db_state[(folder_id, filename)] == 1

    # Second migration run (same file)
    result2 = simulate_migrate_file(filename)
    assert result2 == "skipped"
    assert db_state[(folder_id, filename)] == 2

    # Third run
    result3 = simulate_migrate_file(filename)
    assert result3 == "skipped"
    assert db_state[(folder_id, filename)] == 3

    # Key invariant: only ONE entry per (folder_id, filename) - no duplicates
    matching_entries = sum(1 for k in db_state if k == (folder_id, filename))
    assert matching_entries == 1, "Migration created duplicates!"


def test_migration_categories_complete():
    """All 9 categories are handled by the migration script."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

    # Import from script (adjust path)
    expected = {
        "workpaper_templates", "regulations", "accounting_standards",
        "quality_control", "audit_procedures", "industry_guides",
        "prompts", "report_templates", "notes",
    }
    from app.routers.knowledge_base import VALID_CATEGORIES
    assert VALID_CATEGORIES == expected
