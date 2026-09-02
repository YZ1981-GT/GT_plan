"""Read-only baseline: migration numbering plus the existing version/file distribution.

spec: .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/
Wave 0 Task 8 - Requirements 1.8, 5.12, 14.13

Wave 0 has to re-scan the migration space before Wave 1 adds any table, because the
number space is shared with concurrent sessions and a stale "highest V" from memory is how
two sessions end up writing the same file name. It also records what the *current* version
and artifact-file domains actually look like, so Wave 1's claim of "one business content
revision" has a before-picture rather than a remembered one.

Strictly read-only:

* migration files are read for their names only, never parsed or executed;
* database access is a single read-only transaction of ``SELECT`` statements;
* ``backend/data/amount_input_migration_status.json`` is neither read, written nor staged -
  this spec declares it a concurrency boundary. The file is listed in ``forbidden_paths``
  below purely so the snapshot can assert it was skipped.

Usage from the repository root::

    python backend/scripts/diagnose/probe_task8_migration_version_baseline.py
    python backend/scripts/diagnose/probe_task8_migration_version_baseline.py --out snapshot.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
MIGRATIONS = REPO / "backend" / "migrations"

#: Paths this probe must never touch. Asserted in the snapshot rather than only promised.
FORBIDDEN_PATHS = ("backend/data/amount_input_migration_status.json",)

_VERSION_RE = re.compile(r"^V(\d+)__", re.IGNORECASE)
_ROLLBACK_RE = re.compile(r"^R(\d+)__", re.IGNORECASE)

#: Read-only probes. Every statement is a SELECT; nothing is created or updated.
_QUERIES: dict[str, str] = {
    "file_version_distribution": """
        SELECT file_version, COUNT(*) AS rows
        FROM working_paper
        GROUP BY file_version
        ORDER BY file_version
        LIMIT 50
    """,
    "file_version_summary": """
        SELECT COUNT(*) AS total,
               MIN(file_version) AS min_version,
               MAX(file_version) AS max_version,
               COUNT(*) FILTER (WHERE file_version IS NULL) AS null_version,
               COUNT(*) FILTER (WHERE file_path IS NOT NULL AND file_path <> '') AS with_file_path
        FROM working_paper
    """,
    "parsed_data_version_presence": """
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE parsed_data ? '_version') AS with_private_version,
               COUNT(*) FILTER (WHERE parsed_data ? 'content_revision') AS with_content_revision,
               COUNT(*) FILTER (WHERE parsed_data ? '_migrated_at') AS with_migrated_at,
               COUNT(*) FILTER (WHERE parsed_data IS NULL) AS null_parsed_data
        FROM working_paper
    """,
    "private_version_distribution": """
        SELECT parsed_data->>'_version' AS private_version, COUNT(*) AS rows
        FROM working_paper
        WHERE parsed_data ? '_version'
        GROUP BY 1
        ORDER BY COUNT(*) DESC
        LIMIT 25
    """,
    "file_path_extension_distribution": """
        SELECT lower(right(file_path, 5)) AS tail, COUNT(*) AS rows
        FROM working_paper
        WHERE file_path IS NOT NULL AND file_path <> ''
        GROUP BY 1
        ORDER BY COUNT(*) DESC
        LIMIT 25
    """,
    #: The ledger table is ``schema_version`` (MigrationRunner), not the Flyway-style
    #: ``schema_migrations``. Asking for the wrong name is how a probe reports "no data"
    #: when the truth is "wrong table", so the name is taken from
    #: backend/app/core/migration_runner.py rather than from convention.
    "applied_migrations_summary": """
        SELECT COUNT(*) AS applied_rows,
               MAX(version) AS max_applied_version,
               MAX(applied_at) AS last_applied_at
        FROM schema_version
    """,
    "applied_migrations_tail": """
        SELECT version, filename, applied_at
        FROM schema_version
        ORDER BY applied_at DESC
        LIMIT 15
    """,
}


def scan_migrations(root: Path | None = None) -> dict[str, Any]:
    """Migration file inventory: only names are read, contents are never parsed.

    :param root: directory to scan; defaults to ``backend/migrations``. The parameter
        exists because the real directory currently has a rollback script for every
        forward version, which makes "paired count" and "rollback count" numerically
        identical - a guard reading only the real directory therefore cannot tell a
        by-definition pairing computation from ``len(rollback)``. That was found by
        mutation P03 coming back GREEN, i.e. as an invalid mutation caused by the data
        rather than a guard defect. With a seam, the claim is provable on an orphan case.
    """
    base = root or MIGRATIONS
    if not base.is_dir():
        return {"error": f"missing {base}"}
    forward: dict[int, list[str]] = {}
    rollback: dict[int, list[str]] = {}
    other: list[str] = []
    for path in sorted(base.glob("*.sql")):
        name = path.name
        forward_match = _VERSION_RE.match(name)
        rollback_match = _ROLLBACK_RE.match(name)
        if forward_match:
            forward.setdefault(int(forward_match.group(1)), []).append(name)
        elif rollback_match:
            rollback.setdefault(int(rollback_match.group(1)), []).append(name)
        else:
            other.append(name)
    numbers = sorted(forward)
    duplicates = {str(n): names for n, names in sorted(forward.items()) if len(names) > 1}
    return {
        "forward_file_count": sum(len(v) for v in forward.values()),
        "distinct_forward_versions": len(numbers),
        "max_forward_version": max(numbers) if numbers else None,
        "missing_version_numbers": [
            n for n in range(1, (max(numbers) if numbers else 0) + 1) if n not in forward
        ],
        "duplicate_version_numbers": duplicates,
        "rollback_file_count": sum(len(v) for v in rollback.values()),
        "rollback_versions_without_forward": sorted(
            str(n) for n in rollback if n not in forward
        ),
        "forward_versions_without_rollback_count": sum(
            1 for n in forward if n not in rollback
        ),
        "rollback_paired_count": sum(1 for n in rollback if n in forward),
        "non_versioned_sql_files": other,
        "next_free_version": (max(numbers) + 1) if numbers else 1,
    }


async def _read_database() -> dict[str, Any]:
    """Single read-only transaction. Any failure is recorded as an error, never swallowed."""
    import sys

    sys.path.insert(0, str(REPO / "backend"))
    from sqlalchemy import text  # noqa: PLC0415

    from app.core.database import async_session  # noqa: PLC0415

    out: dict[str, Any] = {}
    async with async_session() as session:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        for name, sql in _QUERIES.items():
            try:
                result = await session.execute(text(sql))
                out[name] = [dict(row._mapping) for row in result]
            except Exception as exc:  # noqa: BLE001 - recorded, not degraded to "no data"
                out[name] = {"error": f"{type(exc).__name__}: {exc}"}
        await session.rollback()
    return out


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def build_snapshot(*, with_database: bool) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "generated_by": "backend/scripts/diagnose/probe_task8_migration_version_baseline.py",
        "spec": "workpaper-html-onlyoffice-bidirectional-writeback-closure",
        "task": "Wave 0 Task 8",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "forbidden_paths": list(FORBIDDEN_PATHS),
        "forbidden_paths_touched": [],
        "migrations": scan_migrations(),
    }
    if with_database:
        try:
            snapshot["database"] = _jsonable(asyncio.run(_read_database()))
        except Exception as exc:  # noqa: BLE001 - an unreachable database is a fact, not a pass
            snapshot["database"] = {"error": f"{type(exc).__name__}: {exc}"}
    else:
        snapshot["database"] = {"skipped": "--no-db"}
    return snapshot


def _print(snapshot: dict[str, Any]) -> None:
    mig = snapshot["migrations"]
    print(
        f"[MIGRATIONS] forward_files={mig.get('forward_file_count')} "
        f"distinct_versions={mig.get('distinct_forward_versions')} "
        f"max_V={mig.get('max_forward_version')} next_free=V{mig.get('next_free_version')}"
    )
    print(
        f"[MIGRATIONS] rollback_files={mig.get('rollback_file_count')} "
        f"paired={mig.get('rollback_paired_count')} "
        f"forward_without_rollback={mig.get('forward_versions_without_rollback_count')}"
    )
    if mig.get("duplicate_version_numbers"):
        print(f"[MIGRATIONS] duplicate V numbers: {mig['duplicate_version_numbers']}")
    if mig.get("missing_version_numbers"):
        missing = mig["missing_version_numbers"]
        print(f"[MIGRATIONS] unused V numbers ({len(missing)}): {missing[:20]}")
    db = snapshot.get("database", {})
    if isinstance(db, dict) and db.get("error"):
        print(f"[DATABASE] unavailable: {db['error']}")
        return
    if isinstance(db, dict) and db.get("skipped"):
        print("[DATABASE] skipped")
        return
    for name, rows in db.items():
        if isinstance(rows, dict) and rows.get("error"):
            print(f"[DATABASE] {name}: {rows['error']}")
        elif isinstance(rows, list):
            head = Counter()
            print(f"[DATABASE] {name}: {len(rows)} row(s)")
            for row in rows[:8]:
                print(f"           {row}")
            del head


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", metavar="PATH", help="write the snapshot JSON here")
    parser.add_argument("--no-db", action="store_true", help="file scan only")
    args = parser.parse_args(argv)
    snapshot = build_snapshot(with_database=not args.no_db)
    _print(snapshot)
    if args.out:
        Path(args.out).write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"[SNAPSHOT] {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
