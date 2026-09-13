"""Task 6 变异：破坏语义 preflight 关键点。"""
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
SEM = ROOT / "backend/app/services/custom_template_ingestion/semantic_preflight.py"
PYTEST_ARGS = [
    sys.executable, "-m", "pytest",
    "tests/custom_template_ingestion/test_semantic_preflight.py",
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
        id="M1-package-gate-always-false",
        file=SEM,
        anchor=r"^def package_blocks_semantic_open\(package: PackageScanResult\) -> bool:$",
        replacement=(
            "def package_blocks_semantic_open(package: PackageScanResult) -> bool:\n"
            "    return False  # mutate\n"
            "def package_blocks_semantic_open_DISABLED(package: PackageScanResult) -> bool:"
        ),
        wants=("test_package_security_blocker_skips_semantic_open",),
        requirement="5.1",
    ),
    Case(
        id="M2-empty-finish-skipped",
        file=SEM,
        anchor=r"^    if not findings:$",
        replacement="    if False and not findings:",
        wants=("test_empty_findings_path_never_valid",),
        requirement="5.7",
    ),
    Case(
        id="M3-guidance-marked-confirmed",
        file=SEM,
        anchor=r'^            "extractionSource": "custom_candidate",$',
        replacement='            "extractionSource": "custom_confirmed",',
        wants=("test_guidance_candidates_are_nine_sections_review_pending",),
        requirement="5.6",
    ),
    Case(
        id="M4-no-carrier-still-editable",
        file=SEM,
        anchor=r"^        return ProjectionRecommendation\.READ_ONLY_HTML  # no-carrier degrade$",
        replacement="        return ProjectionRecommendation.EDITABLE_GRID  # no-carrier degrade",
        wants=("test_no_carrier_recommends_read_only_or_oo_not_editable",),
        requirement="5.5/8.3",
    ),
]


def _count(text: str, pattern: str) -> int:
    return len(re.findall(pattern, text, re.MULTILINE))


def check_anchors() -> int:
    bad = 0
    for case in CASES:
        n = _count(case.file.read_text(encoding="utf-8"), case.anchor)
        status = "OK" if n == 1 else "ANCHOR-MISS"
        if n != 1:
            bad += 1
        print(f"  [{status}] {case.id} (n={n})")
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
