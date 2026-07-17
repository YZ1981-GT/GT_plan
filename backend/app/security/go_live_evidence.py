"""Spec-scoped Evidence Manifest wrapper for ``visibility-isolation-go-live-hardening``.

Task 1 / Requirements 7.1, 7.2, 7.3, 7.4.

The reusable core in :mod:`app.security.evidence_manifest` already parameterizes
``manifest_path`` / ``schema_path`` / ``spec_dir`` on every function — but its module
level constants (``SPEC_DIR`` / ``MANIFEST_PATH`` / ...) and ``empty_manifest()`` point
at the **parent** spec (`procedure-delegation-visibility-isolation`). This thin wrapper
binds the same append-only writer + precheck to **this** spec's own evidence dir so the
two manifests never collide and the parent's usage is left untouched.

Nothing here re-implements the append/precheck/hash logic; it only rebinds paths and the
spec name, and provides ``empty_manifest()`` with the correct ``spec`` constant.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from app.security import evidence_manifest as _em

# ---------------------------------------------------------------------------
# This spec's own evidence paths (independent of the parent manifest).
# ---------------------------------------------------------------------------
_THIS = Path(__file__).resolve()
_REPO_ROOT = _THIS.parents[3]

SPEC_NAME = "visibility-isolation-go-live-hardening"
SPEC_DIR = _REPO_ROOT / ".kiro" / "specs" / SPEC_NAME
EVIDENCE_DIR = SPEC_DIR / "evidence"
MANIFEST_PATH = EVIDENCE_DIR / "manifest.json"
SCHEMA_PATH = EVIDENCE_DIR / "manifest.schema.json"

SCHEMA_VERSION = _em.SCHEMA_VERSION


def empty_manifest() -> dict[str, Any]:
    """An empty manifest carrying **this** spec's name (parent's differs)."""
    return {
        "spec": SPEC_NAME,
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "runs": [],
    }


def load_manifest(manifest_path: Path = MANIFEST_PATH) -> dict[str, Any]:
    if not Path(manifest_path).exists():
        return empty_manifest()
    return _em.load_manifest(manifest_path)


def build_artifact_record(rel_path: str, media_type: str | None = None) -> dict[str, Any]:
    """Build one artifact record (SHA-256 + size) resolved against this spec dir."""
    return _em.build_artifact_record(rel_path, SPEC_DIR, media_type)


def append_run(
    *,
    task_id: str,
    status: str,
    artifacts: Iterable[str | Mapping[str, Any]] = (),
    test_ids: Iterable[str] = (),
    criterion_ids: Iterable[str] = (),
    command: str | None = None,
    run_id: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Append one Criterion_Run to **this** spec's manifest (append-only).

    Delegates to the reusable writer with this spec's ``manifest_path`` / ``spec_dir``
    bound. Existing runs are never mutated.
    """
    return _em.append_run(
        task_id=task_id,
        status=status,
        artifacts=artifacts,
        test_ids=test_ids,
        criterion_ids=criterion_ids,
        command=command,
        run_id=run_id,
        started_at=started_at,
        finished_at=finished_at,
        notes=notes,
        manifest_path=MANIFEST_PATH,
        spec_dir=SPEC_DIR,
    )


def precheck(
    manifest_path: Path = MANIFEST_PATH,
    schema_path: Path = SCHEMA_PATH,
    spec_dir: Path = SPEC_DIR,
) -> list[str]:
    """Validate this spec's manifest (path safety + SHA-256/size + schema). [] == OK."""
    return _em.precheck(manifest_path, schema_path, spec_dir)


def _main() -> int:
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    problems = precheck()
    if problems:
        print(f"[go-live-evidence-precheck] {len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"[go-live-evidence-precheck] OK ({MANIFEST_PATH})")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
