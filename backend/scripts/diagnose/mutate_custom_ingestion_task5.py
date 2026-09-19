"""Task 5 变异检验：破坏 ZIP/XML/OOXML package scanner 关键点，确认守卫真会红。

Spec: custom-workpaper-template-ingestion-and-sync-closure
Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 5.1, 5.7

用法：
    python scripts/diagnose/mutate_custom_ingestion_task5.py --check-anchors
    python scripts/diagnose/mutate_custom_ingestion_task5.py --apply
"""
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
PATHS = ROOT / "backend/app/services/custom_template_ingestion/package_paths.py"
XML = ROOT / "backend/app/services/custom_template_ingestion/package_xml.py"
SCAN = ROOT / "backend/app/services/custom_template_ingestion/package_scanner.py"

PYTEST_ARGS = [
    sys.executable, "-m", "pytest",
    "tests/custom_template_ingestion/test_package_paths.py",
    "tests/custom_template_ingestion/test_package_scanner.py",
    "-q", "-p", "no:randomly",
    "--tb=line",
]
PYTEST_CWD = ROOT / "backend"
ENVPATCH: dict[str, str] = {**os.environ, "PYTHONIOENCODING": "utf-8"}


@dataclass(frozen=True)
class Case:
    id: str
    file: Path
    anchor: str
    replacement: str
    wants: tuple[str, ...]
    requirement: str


CASES: list[Case] = [
    Case(
        id="M1-absolute-path-allowed",
        file=PATHS,
        anchor=r'^    if normalized\.startswith\("/"\):$',
        replacement='    if False and normalized.startswith("/"):',
        wants=("test_absolute_posix_is_rejected",),
        requirement="4.1",
    ),
    Case(
        id="M2-dtd-handler-dropped",
        file=XML,
        anchor=r"^    parser\.StartDoctypeDeclHandler = doctype$",
        replacement="    parser.StartDoctypeDeclHandler = None",
        wants=("test_dtd_is_rejected",),
        requirement="4.2",
    ),
    Case(
        id="M3-empty-report-becomes-complete",
        file=SCAN,
        anchor=r"^    if not findings:$",
        replacement="    if False and not findings:",
        wants=("test_empty_findings_path_never_marks_valid",),
        requirement="5.7",
    ),
    Case(
        id="M4-unknown-feature-not-recorded",
        file=SCAN,
        anchor=r"^        elif decision is FeatureDecision\.BLOCK_PENDING_POLICY:$",
        replacement="        elif False and decision is FeatureDecision.BLOCK_PENDING_POLICY:",
        wants=("test_unknown_content_type_is_block_pending_policy",),
        requirement="4.7",
    ),
    Case(
        id="M5-external-links-path-ignored",
        file=SCAN,
        anchor=r'^    \("xl/externalLinks/", "external_link"\),$',
        replacement='    ("xl/externalLinks-never/", "external_link"),',
        wants=("test_external_links_directory_is_blocker",),
        requirement="4.6",
    ),
    Case(
        id="M6-vba-path-ignored",
        file=SCAN,
        anchor=r'^    \("xl/vbaProject\.bin", "vba_macro"\),$',
        replacement='    ("xl/vbaProject-never.bin", "vba_macro"),',
        wants=("test_vba_project_is_blocker_not_stripped",),
        requirement="4.5",
    ),
    Case(
        id="M7-symlink-attr-ignored",
        file=SCAN,
        anchor=r"^            if is_symlink_external_attr\(info\.external_attr\):$",
        replacement="            if False and is_symlink_external_attr(info.external_attr):",
        wants=("test_symlink_entry_is_blocker",),
        requirement="4.1",
    ),
]


def _count_matches(text: str, pattern: str) -> int:
    return len(re.findall(pattern, text, re.MULTILINE))


def check_anchors() -> int:
    bad = 0
    for case in CASES:
        text = case.file.read_text(encoding="utf-8")
        try:
            n = _count_matches(text, case.anchor)
        except re.error as exc:
            print(f"  [ANCHOR-MISS] {case.id} 正则非法: {exc}")
            bad += 1
            continue
        status = "OK" if n == 1 else "ANCHOR-MISS"
        if n != 1:
            bad += 1
        print(f"  [{status}] {case.id} (n={n})")
    print(f"\nANCHOR-MISS 条数: {bad}/{len(CASES)}")
    return 1 if bad else 0


def run_pytest() -> tuple[int, bytes]:
    proc = subprocess.run(
        PYTEST_ARGS, cwd=str(PYTEST_CWD), capture_output=True, env=ENVPATCH,
    )
    return proc.returncode, proc.stdout


def apply_one(case: Case) -> str:
    text = case.file.read_text(encoding="utf-8")
    n = _count_matches(text, case.anchor)
    if n != 1:
        return f"{case.id}: ANCHOR-MISS (n={n})"
    new_text, cnt = re.subn(case.anchor, case.replacement, text, count=1,
                            flags=re.MULTILINE)
    if cnt != 1:
        return f"{case.id}: ANCHOR-MISS (subn={cnt})"

    backup = case.file.with_suffix(case.file.suffix + ".bak")
    shutil.copy2(case.file, backup)
    try:
        case.file.write_text(new_text, encoding="utf-8")
        rc, out = run_pytest()
        if rc == 0:
            return (f"{case.id}: GREEN FAIL -- guard hole; Requirement "
                    f"{case.requirement} still all-green")
        out_str = out.decode("utf-8", errors="replace")
        hit = [w for w in case.wants if w in out_str]
        if len(hit) != len(case.wants):
            failed = [l for l in out_str.splitlines() if "FAILED" in l][:5]
            return (f"{case.id}: WRONG-TEST FAIL -- expected {case.wants}; "
                    f"actual: {failed}")
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
        print(f"FAIL baseline not green (rc={rc})")
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
