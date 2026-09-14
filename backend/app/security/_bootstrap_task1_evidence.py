"""Bootstrap Task 1 evidence: initial manifest + Task 1 artifacts.

Creates the initial (empty) evidence manifest if absent, and writes the Task 1
artifacts (ledger snapshot + baseline contract snapshot) into the spec evidence
dir. Idempotent. Run: ``python -m app.security._bootstrap_task1_evidence``.

The Task 1 *run record* (with test result) is appended separately by
``_record_task1_run`` after the self-tests pass, so the manifest never claims a
green run before the tests actually run.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from app.security import baseline_contracts as bc
from app.security import evidence_manifest as ev
from app.security.entry_coverage_scanner import LEDGER_PATH

_ARTIFACT_DIR = ev.EVIDENCE_DIR / "artifacts" / "task1"
_LEDGER_SNAPSHOT_REL = "evidence/artifacts/task1/wp_bound_entry_coverage.snapshot.json"
_BASELINE_REL = "evidence/artifacts/task1/baseline_contracts.json"


def bootstrap() -> None:
    _ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    # Initial empty manifest (append-only from here).
    if not ev.MANIFEST_PATH.exists():
        ev.MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        ev.MANIFEST_PATH.write_text(
            json.dumps(ev.empty_manifest(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    # Ledger snapshot artifact (spec-relative, hashable evidence).
    shutil.copyfile(LEDGER_PATH, ev.EVIDENCE_DIR / "artifacts" / "task1" / "wp_bound_entry_coverage.snapshot.json")

    # Baseline contract snapshot artifact.
    (ev.EVIDENCE_DIR / "artifacts" / "task1" / "baseline_contracts.json").write_text(
        json.dumps(bc.get_baseline(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def record_run(status: str, command: str, report_rel: str | None = None) -> dict:
    """Append the Task 1 Criterion_Run. Artifacts are hashed from disk."""
    artifacts: list[str] = [_LEDGER_SNAPSHOT_REL, _BASELINE_REL]
    if report_rel:
        artifacts.append(report_rel)
    return ev.append_run(
        task_id="1",
        status=status,
        artifacts=artifacts,
        test_ids=["backend/tests/security/test_task1_baseline_and_evidence.py"],
        criterion_ids=[
            "2.2", "8.5", "8.17", "13.1", "13.12", "13.13", "15.1", "15.2",
            "15.3", "15.5", "15.6", "15.7", "15.8", "16.21", "16.22", "16.23",
        ],
        command=command,
        notes=(
            "Task 1 baseline inventory + evidence scaffolding. wp-bound entries "
            "recorded as unmigrated (no gate/matrix yet). Migration head V112."
        ),
    )


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    bootstrap()
    print(f"bootstrapped Task 1 evidence under {ev.EVIDENCE_DIR}")
