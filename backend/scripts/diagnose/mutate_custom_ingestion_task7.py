"""Task 7 变异：破坏四 lifecycle 关键点。"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LIFE = ROOT / "backend/app/services/custom_template_ingestion/lifecycles.py"
PYTEST_ARGS = [
    sys.executable, "-m", "pytest",
    "tests/custom_template_ingestion/test_lifecycles.py",
    "-q", "-p", "no:randomly", "--tb=line",
]
PYTEST_CWD = ROOT / "backend"
ENVPATCH = {**os.environ, "PYTHONIOENCODING": "utf-8"}


@dataclass(frozen=True)
class Case:
    id: str
    file: Path
    anchor: str
    replacement: str
    wants: tuple[str, ...]
    requirement: str


CASES = [
    Case(
        id="M1-upload-allows-any-transition",
        file=LIFE,
        anchor=r"^        allowed = _UPLOAD_TRANSITIONS\.get\(self\.state, frozenset\(\)\)$",
        replacement="        allowed = frozenset(UploadArtifactState)",
        wants=("test_upload_transition_matrix_enforced",),
        requirement="6.1/6.5",
    ),
    Case(
        id="M2-frozen-draft-still-editable",
        file=LIFE,
        anchor=r"^        if self\.frozen:$",
        replacement="        if False and self.frozen:",
        wants=("test_draft_optimistic_version_and_freeze_immutable",),
        requirement="6.2",
    ),
    Case(
        id="M3-idempotency-always-new",
        file=LIFE,
        anchor=r"^        existing_id = self\._idempotency\.get\(idempotency_key\)$",
        replacement="        existing_id = None  # mutate: ignore idempotency",
        wants=("test_operation_idempotency_returns_same_record",),
        requirement="6.4/6.5",
    ),
    Case(
        id="M4-lease-expiry-ignored-on-commit",
        file=LIFE,
        anchor=r"^        if self\.lease and self\.lease\.is_expired\(clock\) and to is ProjectOperationState\.COMMITTED:$",
        replacement="        if False and self.lease and self.lease.is_expired(clock) and to is ProjectOperationState.COMMITTED:",
        wants=("test_lease_expiry_blocks_commit_and_watchdog_recovers",),
        requirement="6.6",
    ),
]


def _count(text: str, pattern: str) -> int:
    return len(re.findall(pattern, text, re.MULTILINE))


def check_anchors() -> int:
    bad = 0
    for case in CASES:
        n = _count(case.file.read_text(encoding="utf-8"), case.anchor)
        print(f"  [{'OK' if n == 1 else 'ANCHOR-MISS'}] {case.id} (n={n})")
        if n != 1:
            bad += 1
    print(f"\nANCHOR-MISS: {bad}/{len(CASES)}")
    return 1 if bad else 0


def run_pytest() -> tuple[int, bytes]:
    proc = subprocess.run(
        PYTEST_ARGS, cwd=str(PYTEST_CWD), capture_output=True, env=ENVPATCH,
    )
    return proc.returncode, proc.stdout


def apply_one(case: Case) -> str:
    text = case.file.read_text(encoding="utf-8")
    if _count(text, case.anchor) != 1:
        return f"{case.id}: ANCHOR-MISS"
    new_text, cnt = re.subn(case.anchor, case.replacement, text, count=1, flags=re.MULTILINE)
    if cnt != 1:
        return f"{case.id}: ANCHOR-MISS"
    backup = case.file.with_suffix(case.file.suffix + ".bak")
    shutil.copy2(case.file, backup)
    try:
        case.file.write_text(new_text, encoding="utf-8")
        rc, out = run_pytest()
        if rc == 0:
            return f"{case.id}: GREEN FAIL -- Requirement {case.requirement}"
        out_str = out.decode("utf-8", errors="replace")
        hit = [w for w in case.wants if w in out_str]
        if len(hit) != len(case.wants):
            return f"{case.id}: WRONG-TEST FAIL -- {case.wants}"
        return f"{case.id}: RED OK -- {hit}"
    finally:
        shutil.copy2(backup, case.file)
        backup.unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-anchors", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if args.check_anchors:
        return check_anchors()
    if not args.apply:
        print(__doc__)
        return 0
    rc, out = run_pytest()
    if rc != 0:
        print("FAIL baseline")
        print(out.decode("utf-8", errors="replace")[-2000:])
        return 1
    print("OK baseline green\n")
    bad = 0
    for case in CASES:
        result = apply_one(case)
        print(f"  {result}")
        if "FAIL" in result:
            bad += 1
    print(f"\nbad={bad}/{len(CASES)}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
