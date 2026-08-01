"""Contract test — TabIndex sheet_codes ⊆ ACNR catalog (drift guard).

Task 25.3 (acnr-consumer-wiring). Requirement 18.4:

    A contract test SHALL assert that every `sheet_code` listed in a migrated
    `TabIndex` exists in the ACNR catalog (no orphan/misspelled codes), failing
    CI on drift.

Background
----------
Task 25.2 migrates ``D2TabIndex.vue`` / ``D4TabIndex.vue`` so their displayed
names come from the ACNR catalog, but each component keeps a *local* config
array keyed by ``sheet_code`` (for tabName / applicability / completion
detection). This test guards against orphan or misspelled ``sheet_code`` values
drifting away from the catalog.

Approach
--------
The authoritative code list is read *directly from the two ``.vue`` files* by
regex-extracting the ``code: '...'`` literals of the ``indexRows`` array, so the
test tracks the real components (faithful to the "收集 D2/D4 TabIndex sheet_code
集合" intent). Codes are then partitioned:

* **Catalog-backed sheet codes** — match ``^D\\d+-\\d+$`` (the numbered
  substantive sheets D2-1..D2-13 / D4-1..D4-36). These MUST all exist in the
  ACNR catalog. A misspelling like ``D2-50`` matches this pattern and would
  therefore fail against the catalog → drift caught.

* **Documented pseudo-entries** — everything else. These are legitimately NOT
  ACNR catalog sheet_codes and are enumerated in ``PSEUDO_EXCLUSIONS`` with
  justification below. Any TabIndex code that is neither catalog-backed nor a
  documented pseudo-entry fails the completeness check, forcing a conscious
  classification decision (drift caught the other direction too).

Documented exclusions (justification)
-------------------------------------
* ``附注上市`` / ``附注国企`` / ``D4-附注上市`` / ``D4-附注国企`` — disclosure
  (附注) pseudo-entries, not standalone catalog sheets.
* ``D4-目录`` — the directory tab itself (bundle index), not a catalog sheet.
* ``D4-访谈模板`` — interview-record template, not a catalog sheet.
* ``D2A`` / ``D4A`` / ``D4-22A`` — audit *program tables* (程序表). In the ACNR
  catalog these are folded into the audited-summary sheet_name (e.g. catalog
  ``D2-1`` carries sheet_name "应收账款实质性程序表D2A"); they have no
  standalone ``sheet_code`` entry, so they cannot be sourced from the catalog
  and are display-only local rows.

Requirements: 18.4
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.acnr.catalog import list_sheets

# ─── Paths ────────────────────────────────────────────────────────────────────
# test file: backend/tests/acnr/test_tabindex_codes_in_acnr_catalog.py
#   parents[0]=acnr, [1]=tests, [2]=backend, [3]=<repo root>
_REPO_ROOT = Path(__file__).resolve().parents[3]
_FRONTEND_WP = _REPO_ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper"

_TABINDEX_FILES = {
    "D2TabIndex.vue": _FRONTEND_WP / "d2" / "D2TabIndex.vue",
    "D4TabIndex.vue": _FRONTEND_WP / "d4" / "core" / "D4TabIndex.vue",
}

# ─── Classification ─────────────────────────────────────────────────────────
# A catalog-backed sheet_code is the numbered substantive-sheet form
# (D2-1..D2-13, D4-1..D4-36). Program tables (…A) and Chinese pseudo-entries
# are intentionally excluded — see module docstring.
_CATALOG_CODE_RE = re.compile(r"^D\d+-\d+$")

# Documented pseudo-entries that are legitimately NOT ACNR catalog sheet_codes.
PSEUDO_EXCLUSIONS: set[str] = {
    # disclosure (附注) pseudo-entries
    "附注上市",
    "附注国企",
    "D4-附注上市",
    "D4-附注国企",
    # directory tab (bundle index) and interview template
    "D4-目录",
    "D4-访谈模板",
    # audit program tables (程序表) — folded into审定表 sheet_name in the
    # catalog, no standalone sheet_code
    "D2A",
    "D4A",
    "D4-22A",
}

_CODE_RE = re.compile(r"code:\s*'([^']+)'")


def _extract_tabindex_codes(vue_path: Path) -> list[str]:
    """Regex-extract the ``code: '...'`` literals from a TabIndex .vue file."""
    assert vue_path.exists(), f"TabIndex component not found: {vue_path}"
    text = vue_path.read_text(encoding="utf-8")
    codes = _CODE_RE.findall(text)
    assert codes, f"No sheet_code literals extracted from {vue_path.name}"
    return codes


def _catalog_sheet_codes() -> set[str]:
    """All sheet_code values known to the ACNR catalog."""
    return {s.get("sheet_code", "") for s in list_sheets() if s.get("sheet_code")}


# ─── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("file_name", sorted(_TABINDEX_FILES))
def test_tabindex_codes_in_acnr_catalog(file_name: str) -> None:
    """Every catalog-backed TabIndex sheet_code must exist in the ACNR catalog.

    Requirement 18.4 — no orphan/misspelled codes; fails CI on drift.
    """
    codes = _extract_tabindex_codes(_TABINDEX_FILES[file_name])
    catalog_codes = _catalog_sheet_codes()

    catalog_backed = [c for c in codes if _CATALOG_CODE_RE.match(c)]
    assert catalog_backed, f"{file_name}: no catalog-backed codes extracted"

    missing = sorted({c for c in catalog_backed if c not in catalog_codes})
    assert not missing, (
        f"{file_name}: sheet_code(s) {missing} present in TabIndex but MISSING "
        f"from ACNR catalog (orphan/misspelled — drift). Fix the component code "
        f"or register the sheet in global_catalog.json."
    )


@pytest.mark.parametrize("file_name", sorted(_TABINDEX_FILES))
def test_tabindex_non_catalog_codes_are_documented(file_name: str) -> None:
    """Non-catalog codes must be documented pseudo-entries (completeness guard).

    Catches drift in the other direction: a newly-added code that is neither a
    numbered catalog sheet nor a known pseudo-entry forces a conscious
    classification decision instead of silently slipping through.

    Requirement 18.4
    """
    codes = _extract_tabindex_codes(_TABINDEX_FILES[file_name])

    undocumented = sorted(
        {c for c in codes if not _CATALOG_CODE_RE.match(c) and c not in PSEUDO_EXCLUSIONS}
    )
    assert not undocumented, (
        f"{file_name}: code(s) {undocumented} are neither catalog-backed "
        f"(^D\\d+-\\d+$) nor listed in PSEUDO_EXCLUSIONS. If this is a real "
        f"catalog sheet, ensure it exists in the catalog; if it is a pseudo-"
        f"entry (disclosure/directory/program-table), add it to PSEUDO_EXCLUSIONS "
        f"with justification."
    )
