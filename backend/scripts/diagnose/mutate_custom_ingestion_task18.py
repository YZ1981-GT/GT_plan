#!/usr/bin/env python3
"""Task 18 定向变异（custom Task 10–17 新增模块）。

用法:
  python backend/scripts/diagnose/mutate_custom_ingestion_task18.py --check-anchors
  python backend/scripts/diagnose/mutate_custom_ingestion_task18.py --run
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
REPORT = (
    REPO
    / ".kiro"
    / "specs"
    / "custom-workpaper-template-ingestion-and-sync-closure"
    / "basis"
    / "T18-mutation-report.json"
)

TARGETS: dict[str, Path] = {
    "M_PWI_NO_SHEET_COPY": BACKEND
    / "app/services/custom_template_ingestion/workbook_instance.py",
    "M_NS_GATE": BACKEND
    / "app/services/custom_template_ingestion/namespace_migration.py",
    "M_SAGA_ACTIVE": BACKEND
    / "app/services/custom_template_ingestion/finalize_saga.py",
    "M_CAS_BASE": BACKEND / "app/services/custom_template_ingestion/staging_cas.py",
    "M_NO_LWW": BACKEND / "app/services/custom_template_ingestion/merge_remap.py",
}

ANCHORS: dict[str, str] = {
    "M_PWI_NO_SHEET_COPY": 'raise WorkbookInstanceError("至少纳入一个 sheet")',
    "M_NS_GATE": "raise NamespaceSplitError(",
    "M_SAGA_ACTIVE": 'f"instantiate 仅允许 ACTIVE publication',
    "M_CAS_BASE": 'f"client base mismatch: client={payload.client_content_revision} "',
    "M_NO_LWW": "blocked=bool(conflicts)",
}

# (old, new) — each must leave baseline GREEN and make subset RED
MUTATIONS: dict[str, tuple[str, str]] = {
    "M_PWI_NO_SHEET_COPY": (
        'raise WorkbookInstanceError("至少纳入一个 sheet")',
        "pass  # mutated: allow empty workbook",
    ),
    "M_NS_GATE": (
        "raise NamespaceSplitError(",
        "return  # mutated: pretend namespace unified\n        raise NamespaceSplitError(",
    ),
    "M_SAGA_ACTIVE": (
        "if publication.state != PublicationState.ACTIVE:\n"
        "        raise FinalizeSagaError(\n"
        '            f"instantiate 仅允许 ACTIVE publication，当前={publication.state.value}"\n'
        "        )",
        "return  # mutated: allow instantiate non-ACTIVE",
    ),
    "M_CAS_BASE": (
        "raise StagingCasError(\n"
        '                f"client base mismatch: client={payload.client_content_revision} "\n'
        '                f"server={current_revision}"\n'
        "            )",
        "return  # mutated: ignore client base",
    ),
    "M_NO_LWW": (
        "blocked=bool(conflicts)",
        "blocked=False  # mutated: LWW ignore conflicts",
    ),
}

TEST_CMD = [
    sys.executable,
    "-m",
    "pytest",
    "tests/custom_template_ingestion/test_workbook_instance.py",
    "tests/custom_template_ingestion/test_finalize_saga.py",
    "tests/custom_template_ingestion/test_staging_cas.py",
    "tests/custom_template_ingestion/test_merge_publication_retention.py",
    "tests/custom_template_ingestion/test_sync_gates.py",
    "-q",
    "--tb=no",
]


def _utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass


def _check_anchors() -> int:
    miss = 0
    for mid, needle in ANCHORS.items():
        text = TARGETS[mid].read_text(encoding="utf-8")
        ok = needle in text
        print(f"[{'OK  ' if ok else 'MISS'}] {mid}")
        if not ok:
            miss += 1
    print(f"锚点自检：{len(ANCHORS) - miss}/{len(ANCHORS)} OK，{miss} MISS")
    return miss


def _pytest() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        TEST_CMD,
        cwd=BACKEND,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _apply(mid: str) -> str:
    path = TARGETS[mid]
    old, new = MUTATIONS[mid]
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"{mid}: mutation anchor missing in {path.name}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return text


def _restore(mid: str, original: str) -> None:
    TARGETS[mid].write_text(original, encoding="utf-8")


def _run() -> int:
    miss = _check_anchors()
    if miss:
        return 1

    baseline = _pytest()
    if baseline.returncode != 0:
        print("基线 RED — 拒绝变异")
        print(baseline.stdout[-800:] if baseline.stdout else "")
        return 1
    print("基线 GREEN")

    rows: list[dict] = []
    all_red = True
    for mid in MUTATIONS:
        original = _apply(mid)
        try:
            proc = _pytest()
            red = proc.returncode != 0
            verdict = "RED" if red else "GREEN_FAIL"
            if not red:
                all_red = False
            print(f"[{verdict}] {mid}")
            rows.append(
                {
                    "id": mid,
                    "target": str(TARGETS[mid].relative_to(REPO)).replace("\\", "/"),
                    "verdict": verdict,
                    "returncode": proc.returncode,
                }
            )
        finally:
            _restore(mid, original)

    # post-restore sanity
    post = _pytest()
    if post.returncode != 0:
        print("恢复后基线 RED — 工作树可能污染")
        all_red = False

    payload = {
        "task": 18,
        "spec": "custom-workpaper-template-ingestion-and-sync-closure",
        "recordedAt": datetime.now(UTC).isoformat(),
        "baselinePassed": baseline.returncode == 0,
        "postRestorePassed": post.returncode == 0,
        "mutations": rows,
        "allRed": all_red and len(rows) == len(MUTATIONS),
        "redCount": sum(1 for r in rows if r["verdict"] == "RED"),
        "total": len(MUTATIONS),
        "scopeNotes": [
            "Non-OO / non-Playwright module mutations only",
            "SYNC gates and true OO dual-user Playwright remain BLOCKED for Task 18 closure",
        ],
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"result {payload['redCount']}/{payload['total']} RED "
        f"allRed={payload['allRed']} report={REPORT}"
    )
    return 0 if payload["allRed"] else 1


def main(argv: list[str] | None = None) -> int:
    _utf8()
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-anchors", action="store_true")
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args(argv)
    if args.check_anchors:
        return 0 if _check_anchors() == 0 else 1
    if args.run:
        return _run()
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
