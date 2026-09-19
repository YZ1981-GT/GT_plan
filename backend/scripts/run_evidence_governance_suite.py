#!/usr/bin/env python
"""Single aggregation entrypoint for the evidence-governance backend suite.

Spec: attachment-ocr-ai-evidence-governance-hardening (Task 8.3)

Runs the whole evidence-governance backend suite (unit / integration / API /
component) in one command, covering scope isolation, transaction boundaries,
idempotency, worker crash / dead-letter, watermark contention, migration
interruption and fail-closed behavior.

Membership is the ``evidence_governance`` pytest marker (auto-applied in
``tests/conftest.py`` by path + embedded spec slug). This script constrains
pytest collection to the exact evidence paths so it never trips on unrelated,
pre-existing collection errors elsewhere in ``tests/``.

Usage (Windows PowerShell)::

    # fast local run (few Hypothesis examples)
    $env:HYPOTHESIS_MAX_EXAMPLES=1; python scripts/run_evidence_governance_suite.py

    # pass extra pytest args through
    python scripts/run_evidence_governance_suite.py -q --tb=line

    # nightly / release: raise sample count
    $env:HYPOTHESIS_MAX_EXAMPLES=50; python scripts/run_evidence_governance_suite.py

Equivalent bare marker command (may surface unrelated pre-existing collection
errors, which are deselected)::

    python -m pytest -m evidence_governance --continue-on-collection-errors

The global ``fast`` Hypothesis profile in ``tests/conftest.py`` already reads
``HYPOTHESIS_MAX_EXAMPLES``; this script never edits test source to change
example counts.
"""
from __future__ import annotations

import glob
import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
TESTS = BACKEND / "tests"


def _collect_paths() -> list[str]:
    paths: list[str] = []

    # 1) named wave locations (directories)
    for d in ("evidence_governance", "attachment_ocr_ai_evidence_governance_hardening"):
        p = TESTS / d
        if p.is_dir():
            paths.append(str(p))

    # 2) flat spec files by glob (named + wave 3/4/5 ref/OCR/AI)
    globs = (
        "test_evidence_governance_*.py",
        "test_evidence_ref_*.py",
        "test_evidence_typed_adapters_contract.py",
        "test_evidence_role_capability_contract.py",
        "test_evidence_file_path_boundary_contract.py",
        "test_ocr_governance_*.py",
        "test_ocr_retry_service_task5_2.py",
        "test_ai_evidence_gate.py",
    )
    for g in globs:
        paths.extend(sorted(glob.glob(str(TESTS / g))))

    # de-dup while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def main(argv: list[str]) -> int:
    paths = _collect_paths()
    if not paths:
        print("[run_evidence_governance_suite] no evidence-governance test paths found", file=sys.stderr)
        return 2

    os.environ.setdefault("HYPOTHESIS_MAX_EXAMPLES", "5")

    cmd = [
        sys.executable, "-m", "pytest",
        "-m", "evidence_governance",
        "-p", "no:cacheprovider",
        *paths,
        *argv,
    ]
    print("[run_evidence_governance_suite] HYPOTHESIS_MAX_EXAMPLES=%s" % os.environ.get("HYPOTHESIS_MAX_EXAMPLES"))
    print("[run_evidence_governance_suite] running %d path(s)" % len(paths))
    return subprocess.call(cmd, cwd=str(BACKEND))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
