"""Reverse-dup scanner conformance for G-C0 (Req 1.2).

Downstream specs MUST import the eight C0 top-level symbols from the
backend bundle (Python) and its frontend TypeScript binding (once landed).
Any local ``interface Foo`` / ``type Foo`` / ``class Foo`` re-declaration
of a C0 top-level symbol is a contract violation that must fail conformance.

The current baseline has two known, sanctioned exemptions tied to the
``workpaper-page-formula-toolbar-closure`` F1 migration. They are
recorded as TODOs here so any NEW dupe outside this exemption list turns
the guard RED.

See ``.kiro/specs/workpaper-guidance-content-closure/requirements.md
Requirement 1.2`` and ``design.md §1.8``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.guidance_gc0_contract import (
    GC0_TOP_LEVEL_TYPES,
    discover_local_dupes,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "audit-platform" / "frontend" / "src"
# Frontend TS binding owner directory — same rule as ``bundle_root()`` on the
# backend: this directory is the legitimate home of the C0 TS type
# declarations. The scanner skips it via ``ts_owner_dir``; only duplicates
# outside this directory (and outside the backend bundle) are violations.
FRONTEND_GC0_OWNER = FRONTEND_SRC / "shared" / "contracts" / "gc0"

#: Known, sanctioned duplicates. Key = (file_stem, symbol).
#: Value = owner + rationale (TODO link to the migration spec).
#:
#: Every entry here MUST carry a TODO reference to a downstream spec that
#: will migrate the symbol off the local copy. New entries MUST be
#: reviewed; do not add exemptions just to keep tests green.
#:
#: Empty since the F1 migration: ``guidancePanelStore`` and ``GtCControlTest``
#: no longer re-declare ``GuidanceSection`` — both now carry explicitly named
#: local payload types (``RuntimeGuidanceSectionPayload`` / the render-config
#: amber block) that are documented as *not* the G-C0 wire type.
ALLOWED_EXEMPTIONS: dict[tuple[str, str], str] = {}


def _key_of_dup(dup_file: str, dup_symbol: str) -> tuple[str, str]:
    """Normalize a finding to the (file_stem, symbol) key used in exemptions."""
    return (Path(dup_file).stem, dup_symbol)


def _run_scan() -> tuple:
    """Run the reverse-dup scanner against the frontend source root.

    Skips the whole repo root so the backend bundle never shows up.
    Skips the frontend TS binding owner directory — files under
    ``src/shared/contracts/gc0`` are the legitimate TS home of the C0
    types and are not duplicates by definition.
    """
    if not FRONTEND_SRC.exists():
        pytest.skip(f"frontend src root not present at {FRONTEND_SRC}")
    return discover_local_dupes(
        [FRONTEND_SRC],
        ts_owner_dir=FRONTEND_GC0_OWNER if FRONTEND_GC0_OWNER.exists() else None,
    )


def test_reverse_dup_scan_returns_typed_findings() -> None:
    """Smoke: the scanner must return a tuple of findings without raising.

    **Validates: Requirements 1.2**
    """
    findings = _run_scan()
    assert isinstance(findings, tuple), "scanner must return a tuple"
    for f in findings:
        assert f.symbol in GC0_TOP_LEVEL_TYPES, (
            f"scanner returned a symbol not in GC0_TOP_LEVEL_TYPES: {f.symbol!r}"
        )
        assert f.kind in {"interface", "type", "class", "json-schema-copy"}, (
            f"unexpected kind '{f.kind}' for {f.file!r}::{f.symbol!r}"
        )


def test_all_duplicates_are_covered_by_exemptions() -> None:
    """Every finding must appear in ALLOWED_EXEMPTIONS; new dupes turn RED.

    This is the fail-closed guard: any new local re-declaration of a C0
    top-level symbol outside the documented exemptions will surface here.

    **Validates: Requirements 1.2**
    """
    findings = _run_scan()
    uncovered: list[tuple[str, str, str]] = []
    for f in findings:
        key = _key_of_dup(f.file, f.symbol)
        if key not in ALLOWED_EXEMPTIONS:
            uncovered.append((f.file, f.symbol, f.kind))

    assert not uncovered, (
        "New unapproved G-C0 duplicate(s) detected outside "
        "ALLOWED_EXEMPTIONS — every local re-declaration of a C0 top-level "
        f"symbol must be imported from the shared bundle:\n"
        f"  findings: {[{'file': f, 'symbol': s, 'kind': k} for f, s, k in uncovered]}\n"
        f"  allowed exemptions: {sorted(ALLOWED_EXEMPTIONS.keys())}"
    )


def test_documented_exemptions_still_match_scanner_output() -> None:
    """Every entry in ALLOWED_EXEMPTIONS must currently be a real finding.

    Stale exemptions indicate the underlying duplicate was migrated and the
    exemption record has not been cleaned up. Removing a stale exemption is
    the desired follow-up action.
    """
    findings = _run_scan()
    found_keys = {_key_of_dup(f.file, f.symbol) for f in findings}
    stale = sorted(set(ALLOWED_EXEMPTIONS.keys()) - found_keys)
    assert not stale, (
        "ALLOWED_EXEMPTIONS contains entries that no longer match a real "
        f"duplicate on disk; migrate the exemption to a completed ticket:\n"
        f"  stale: {stale}"
    )


def test_expected_baseline_of_zero_exemptions() -> None:
    """Baseline: no findings and no exemptions after the F1 migration.

    This is a soft baseline assertion. Any newly introduced duplicate must
    either be migrated or added to ALLOWED_EXEMPTIONS with a TODO, and this
    baseline adjusted in the same PR.
    """
    findings = _run_scan()
    # Baseline count — this number MUST stay aligned with ALLOWED_EXEMPTIONS.
    assert len(findings) == len(ALLOWED_EXEMPTIONS) == 0, (
        f"expected exactly {len(ALLOWED_EXEMPTIONS)} duplicate findings, "
        f"got {len(findings)}. Findings: "
        f"{[{'file': f.file, 'symbol': f.symbol, 'kind': f.kind} for f in findings]}"
    )


def test_scanner_separates_type_only_imports_from_redeclarations(tmp_path) -> None:
    """The guard must stay fail-closed after the declaration-form fix.

    A naive ``"type Foo" in line`` scan also matched ``import { type Foo }``,
    which is the *compliant* pattern — so every correct consumer looked like a
    violation and the baseline could only be kept green by exempting them.
    Both directions are asserted here so a future relaxation cannot silently
    turn the scanner into a no-op.

    **Validates: Requirements 1.2**
    """
    symbol = next(iter(GC0_TOP_LEVEL_TYPES))

    compliant = tmp_path / "compliant.ts"
    compliant.write_text(
        "import {\n"
        f"  type {symbol},\n"
        "} from '@/shared/contracts/gc0'\n"
        f"export function use(x: {symbol}) {{ return x }}\n",
        encoding="utf-8",
    )
    assert discover_local_dupes([tmp_path]) == (), (
        "type-only import of a C0 symbol must not be reported as a duplicate"
    )

    for source in (
        f"export type {symbol} = {{ id: string }}\n",
        f"type {symbol}<T> = {{ value: T }}\n",
        f"export interface {symbol} {{ id: string }}\n",
        f"export abstract class {symbol} {{}}\n",
    ):
        violation = tmp_path / "violation.ts"
        violation.write_text(source, encoding="utf-8")
        findings = [f for f in discover_local_dupes([tmp_path]) if f.symbol == symbol]
        assert findings, f"local re-declaration must stay RED: {source!r}"
        violation.unlink()


# ---------------------------------------------------------------------------
# Terminal summary: print all findings so the terminal output doubles as
# the reverse-scan report required by the task spec.
# ---------------------------------------------------------------------------


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    if not FRONTEND_SRC.exists():
        terminalreporter.section("G-C0 Reverse-Dup Scan (frontend src)")
        terminalreporter.write_line(f"  root: {FRONTEND_SRC}")
        terminalreporter.write_line("  skipped: root not present")
        return
    findings = _run_scan()
    terminalreporter.section("G-C0 Reverse-Dup Scan (frontend src)")
    terminalreporter.write_line(f"  root: {FRONTEND_SRC}")
    terminalreporter.write_line(f"  total findings: {len(findings)}")
    for f in findings:
        key = _key_of_dup(f.file, f.symbol)
        marker = "EXEMPTED" if key in ALLOWED_EXEMPTIONS else "UNCOVERED"
        line = f"  [{marker:<9}] {f.symbol} @ {f.file}:{f.line} ({f.kind})"
        if marker == "EXEMPTED":
            line += f"  — {ALLOWED_EXEMPTIONS[key]}"
        terminalreporter.write_line(line)
