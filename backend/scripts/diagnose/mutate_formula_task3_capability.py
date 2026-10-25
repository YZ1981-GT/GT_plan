"""Task 3 mutations: capability gate must stay fail-closed."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SVC = ROOT / "backend/app/services/workpaper_capability/__init__.py"
FE = ROOT / "audit-platform/frontend/src/shell/formula/workpaperCapabilitySnapshot.ts"
PYTEST_CWD = ROOT / "backend"
VITEST_CWD = ROOT / "audit-platform/frontend"
ENVPATCH = {**os.environ, "PYTHONIOENCODING": "utf-8"}


@dataclass(frozen=True)
class MutCase:
    id: str
    file: Path
    anchor: str
    replacement: str
    wants: tuple[str, ...]
    runner: str
    literal: bool = True


CASES = [
    MutCase(
        id="M1-ignore-project-member",
        file=SVC,
        anchor=(
            "    if not principal.project_member:\n"
            "        return _deny(\"not_project_member\")\n"
        ),
        replacement="    # mutation: project membership ignored\n",
        wants=("test_not_member_and_invisible_fail_closed",),
        runner="pytest",
    ),
    MutCase(
        id="M2-skip-expiry-check",
        file=SVC,
        anchor="    if clock >= expires:\n        return _deny(\"snapshot_expired\")\n",
        replacement="    # mutation: expiry ignored\n",
        wants=("test_gate_blocks_uninitialized_expired_and_epoch_mismatch",),
        runner="pytest",
    ),
    MutCase(
        id="M3-client-treat-null-as-allowed",
        file=FE,
        anchor="  if (!snapshot) return blocked('snapshot_uninitialized')\n",
        replacement="  if (!snapshot) return { status: 'allowed' }\n",
        wants=("blocks uninitialized",),
        runner="vitest",
    ),
]


def _count(text: str, pattern: str) -> int:
    return text.count(pattern)


def check_anchors() -> int:
    bad = 0
    for case in CASES:
        n = _count(case.file.read_text(encoding="utf-8"), case.anchor)
        print(f"  [{'OK' if n == 1 else 'ANCHOR-MISS'}] {case.id} (n={n})")
        if n != 1:
            bad += 1
    return 1 if bad else 0


def run_case(case: MutCase) -> tuple[int, str]:
    if case.runner == "pytest":
        cmd = (
            f"{sys.executable} -m pytest tests/test_workpaper_capability_snapshot.py "
            f"-q -p no:randomly --tb=line"
        )
        cwd = PYTEST_CWD
    else:
        cmd = (
            "npx vitest run "
            "src/shell/formula/__tests__/workpaperCapabilitySnapshot.spec.ts"
        )
        cwd = VITEST_CWD
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, env=ENVPATCH, shell=True)
    out = (proc.stdout or b"").decode("utf-8", errors="replace") + (
        proc.stderr or b""
    ).decode("utf-8", errors="replace")
    return proc.returncode, out


def apply_one(case: MutCase) -> str:
    text = case.file.read_text(encoding="utf-8")
    if _count(text, case.anchor) != 1:
        return f"{case.id}: ANCHOR-MISS"
    new_text = text.replace(case.anchor, case.replacement, 1)
    if new_text == text:
        return f"{case.id}: ANCHOR-MISS"
    backup = case.file.with_suffix(case.file.suffix + ".bak")
    shutil.copy2(case.file, backup)
    try:
        case.file.write_text(new_text, encoding="utf-8")
        rc, out = run_case(case)
        if rc == 0:
            return f"{case.id}: GREEN FAIL"
        hit = [w for w in case.wants if w in out]
        if len(hit) != len(case.wants):
            return f"{case.id}: WRONG-TEST FAIL\n{out[-1500:]}"
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
    for runner in ("pytest", "vitest"):
        dummy = MutCase(
            id="baseline",
            file=SVC,
            anchor="x",
            replacement="x",
            wants=(),
            runner=runner,
        )
        rc, out = run_case(dummy)
        if rc != 0:
            print(f"baseline {runner} not green")
            print(out[-2000:])
            return 1
    print("OK baseline green")
    bad = 0
    for case in CASES:
        result = apply_one(case)
        print(f"  {result}")
        if "RED OK" not in result:
            bad += 1
    print(f"\nbad={bad}/{len(CASES)}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
