"""G-ID 变异：破坏 registry fail-closed / 六类登记。"""
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
GID = ROOT / "backend/app/services/guidance_gid.py"
PYTEST_ARGS = [
    sys.executable, "-m", "pytest",
    "tests/test_guidance_gid.py",
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


CASES = [
    Case(
        id="M1-unknown-kind-allowed",
        file=GID,
        anchor=r'^                "kind_unknown",$',
        replacement='                "kind_unknown_disabled",',
        wants=("test_unknown_kind_fail_closed",),
    ),
    Case(
        id="M2-lifecycle-kind-allowed",
        file=GID,
        anchor=r"^        if kind in FORBIDDEN_LIFECYCLE_KIND_NAMES:$",
        replacement="        if False and kind in FORBIDDEN_LIFECYCLE_KIND_NAMES:",
        wants=("test_lifecycle_name_as_kind_fail_closed",),
    ),
    Case(
        id="M3-allow-custom-artifact-physical-path",
        file=GID,
        anchor=r'^        if any\(k in raw for k in \("path", "storageKey", "storage_key", "absolutePath"\)\):$',
        replacement='        if False and any(k in raw for k in ("path", "storageKey", "storage_key", "absolutePath")):',
        wants=("test_custom_artifact_rejects_physical_path",),
    ),
    Case(
        id="M4-publication-lookup-optional",
        file=GID,
        anchor=r"^        if lookup is None:$",
        replacement="        if False and lookup is None:",
        wants=("test_methodology_publication_requires_lookup",),
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
            return f"{case.id}: GREEN FAIL"
        out_str = out.decode("utf-8", errors="replace")
        hit = [w for w in case.wants if w in out_str]
        if len(hit) != len(case.wants):
            return f"{case.id}: WRONG-TEST FAIL"
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
    rc, _ = run_pytest()
    if rc != 0:
        print("FAIL baseline")
        return 1
    print("OK baseline green\n")
    bad = 0
    for case in CASES:
        result = apply_one(case)
        print(f"  {result}")
        if "FAIL" in result or "MISS" in result:
            bad += 1
    print(f"\nbad={bad}/{len(CASES)}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
