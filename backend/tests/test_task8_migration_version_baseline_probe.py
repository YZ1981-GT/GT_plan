"""Guards for the read-only migration / version baseline probe.

spec: .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/
Wave 0 Task 8 - Requirements 1.8, 5.12, 14.13

Three claims are worth locking down:

* the file scan reports what is actually on disk (independently re-derived here, so a
  drifting regex or an off-by-one on the highest version is visible);
* the accounting is exhaustive - every ``.sql`` file lands in exactly one bucket, so a
  file the probe cannot classify is reported instead of dropped;
* the concurrency boundary holds. ``backend/data/amount_input_migration_status.json`` is
  declared out of bounds for this spec, and the probe must not read, write or stage it.
  This is asserted structurally - the filename may appear in the module only as the
  declared forbidden constant - because reading the file to compare a digest would itself
  be the thing the boundary forbids.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend" / "scripts" / "diagnose"))

import probe_task8_migration_version_baseline as probe  # noqa: E402

MIGRATIONS = REPO / "backend" / "migrations"
PROBE_SOURCE = REPO / "backend" / "scripts" / "diagnose" / "probe_task8_migration_version_baseline.py"
FORBIDDEN_NAME = "amount_input_migration_status.json"


def _sql_files() -> list[str]:
    return sorted(path.name for path in MIGRATIONS.glob("*.sql"))


def test_scan_reports_the_real_migration_files() -> None:
    """Independent derivation: counts, highest version and next free slot."""
    files = _sql_files()
    forward = [f for f in files if re.match(r"^V(\d+)__", f, re.IGNORECASE)]
    numbers = sorted(int(re.match(r"^V(\d+)__", f, re.IGNORECASE).group(1)) for f in forward)
    scan = probe.scan_migrations()
    assert files, "the migrations directory is empty - the guard would be vacuous"
    assert scan["forward_file_count"] == len(forward)
    assert scan["max_forward_version"] == max(numbers)
    assert scan["next_free_version"] == max(numbers) + 1
    assert scan["distinct_forward_versions"] == len(set(numbers))


def test_every_sql_file_lands_in_exactly_one_bucket() -> None:
    """Exhaustive accounting: a file the probe cannot classify must surface, not vanish."""
    scan = probe.scan_migrations()
    counted = (
        scan["forward_file_count"]
        + scan["rollback_file_count"]
        + len(scan["non_versioned_sql_files"])
    )
    assert counted == len(_sql_files()), (
        f"{len(_sql_files())} .sql files on disk but only {counted} accounted for"
    )


def test_rollback_pairing_is_measured_against_forward_versions() -> None:
    files = _sql_files()
    forward_numbers = {
        int(m.group(1)) for f in files if (m := re.match(r"^V(\d+)__", f, re.IGNORECASE))
    }
    rollback_numbers = {
        int(m.group(1)) for f in files if (m := re.match(r"^R(\d+)__", f, re.IGNORECASE))
    }
    scan = probe.scan_migrations()
    assert scan["rollback_paired_count"] == len(rollback_numbers & forward_numbers)
    assert scan["rollback_versions_without_forward"] == sorted(
        str(n) for n in rollback_numbers - forward_numbers
    )
    assert scan["forward_versions_without_rollback_count"] == len(
        forward_numbers - rollback_numbers
    )


def test_orphan_rollback_script_is_not_counted_as_paired(tmp_path: Path) -> None:
    """Pairing is computed against forward versions, not simply counted.

    The real directory happens to have a rollback for every forward version, so on real
    data ``len(rollback)`` and "how many rollbacks have a forward counterpart" are the same
    number. That coincidence makes the claim untestable there - hence the synthetic case
    with one orphan ``R``.
    """
    for name in ("V001__init.sql", "R001__rollback_init.sql", "R999__orphan_rollback.sql"):
        (tmp_path / name).write_text("-- fixture\n", encoding="utf-8")
    scan = probe.scan_migrations(tmp_path)
    assert scan["forward_file_count"] == 1
    assert scan["rollback_file_count"] == 2
    assert scan["rollback_paired_count"] == 1, "an orphan rollback must not count as paired"
    assert scan["rollback_versions_without_forward"] == ["999"]
    assert scan["forward_versions_without_rollback_count"] == 0
    assert scan["next_free_version"] == 2


def test_snapshot_declares_the_read_only_contract() -> None:
    snapshot = probe.build_snapshot(with_database=False)
    assert snapshot["read_only"] is True
    assert snapshot["forbidden_paths_touched"] == []
    assert any(FORBIDDEN_NAME in path for path in snapshot["forbidden_paths"])
    assert snapshot["database"] == {"skipped": "--no-db"}


def test_forbidden_path_appears_only_as_the_declared_constant() -> None:
    """The boundary is structural: the name may appear only inside ``FORBIDDEN_PATHS``.

    Parsed with AST rather than grepped, so a mention inside a comment or docstring is not
    counted while a real ``open()`` on it would be. The point is that no code path can read
    the file, which is what this spec's concurrency boundary demands.
    """
    tree = ast.parse(PROBE_SOURCE.read_text(encoding="utf-8"))
    declared: list[ast.Constant] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "FORBIDDEN_PATHS" for t in node.targets
        ):
            declared = [n for n in ast.walk(node.value) if isinstance(n, ast.Constant)]
    assert declared, "FORBIDDEN_PATHS is not declared - the boundary would be undocumented"
    #: Docstrings are Constant nodes too, and prose *about* the boundary is exactly what we
    #: want the module to contain. Only executable references count.
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    exempt = {id(node) for node in declared} | docstrings
    stray = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and FORBIDDEN_NAME in node.value
        and id(node) not in exempt
    ]
    assert not stray, (
        f"{FORBIDDEN_NAME} referenced outside FORBIDDEN_PATHS: {stray} - "
        "this spec must not read, write or stage that file"
    )


def test_every_database_query_is_read_only() -> None:
    """No probe query may write. A SELECT-only shape is checkable without a database."""
    offenders = [
        name
        for name, sql in probe._QUERIES.items()
        if not sql.strip().upper().startswith("SELECT")
        or re.search(r"\b(INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|TRUNCATE)\b", sql.upper())
    ]
    assert not offenders, f"non read-only probe queries: {offenders}"
