"""Task 8 变异：破坏 mapping / identity / adapter 关键裁决点。

用法:
  python backend/scripts/diagnose/mutate_custom_ingestion_task8.py --check-anchors
  python backend/scripts/diagnose/mutate_custom_ingestion_task8.py --apply

每个 case 单点破坏一个真源，期望对应守卫变 RED（且只命中预期测试）。
四态: RED OK / GREEN FAIL / WRONG-TEST FAIL / ANCHOR-MISS。
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
BASE = ROOT / "backend/app/services/custom_template_ingestion"
IDENT = BASE / "identity.py"
MAP = BASE / "mapping.py"
ADAPT = BASE / "adapters.py"

PYTEST_ARGS = [
    sys.executable, "-m", "pytest",
    "tests/custom_template_ingestion/test_mapping_adapters.py",
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
    # ── identity ──
    Case(
        id="M1-label-accepted-as-carrier",
        file=IDENT,
        anchor=r"^        if folded in NON_CARRIER_SIGNALS:$",
        replacement="        if False and folded in NON_CARRIER_SIGNALS:",
        wants=("test_label_and_index_are_never_identity_carriers",),
        requirement="7.5",
    ),
    Case(
        id="M2-instrumented-candidate-reuses-old-revision",
        file=IDENT,
        anchor=r'^        if self\.new_candidate_revision == self\.base_candidate_revision:$',
        replacement="        if False:",
        wants=("test_instrumented_candidate_rejects_equal_revision_directly",),
        requirement="8.2",
    ),
    Case(
        id="M3-instrumented-candidate-reuses-old-digest",
        file=IDENT,
        anchor=r'^        if self\.new_artifact_sha256 == self\.base_artifact_sha256:$',
        replacement="        if False:",
        wants=("test_instrumented_candidate_rejects_equal_digest_directly",
               "test_instrument_candidate_rejects_writer_that_does_not_change_bytes"),
        requirement="8.2",
    ),
    Case(
        id="M4-noninstrumentable-kind-allowed",
        file=IDENT,
        anchor=r"^    if kind not in INSTRUMENTABLE_CARRIER_KINDS:$",
        replacement="    if False and kind not in INSTRUMENTABLE_CARRIER_KINDS:",
        wants=("test_instrumentation_rejects_noninstrumentable_kind",),
        requirement="8.2",
    ),
    Case(
        id="M5-unverified-instrumentation-supports-editable",
        file=IDENT,
        anchor=r"^        return instrumented is not None and instrumented\.verified$",
        replacement="        return instrumented is not None",
        wants=("test_unverified_instrumentation_cannot_support_editable_grid",),
        requirement="8.3",
    ),
    # ── mapping: mode / manifest ──
    Case(
        id="M6-no-carrier-keeps-editable",
        file=MAP,
        anchor=r"^    return ProjectionMode\.READ_ONLY_HTML$",
        replacement="    return ProjectionMode.EDITABLE_GRID",
        wants=("test_no_carrier_downgrades_editable_to_read_only",
               "test_included_editable_without_carrier_downgrades_and_drops_managed"),
        requirement="8.3",
    ),
    Case(
        id="M7-editable-allows-null-adapter",
        file=MAP,
        anchor=r"^        if adapter is None:$",
        replacement="        if False:",
        wants=("test_editable_grid_requires_nonnull_adapter",),
        requirement="8.4",
    ),
    Case(
        id="M8-read-only-allows-managed-field",
        file=MAP,
        anchor=r'^                code="read_only_declares_managed_field",$',
        replacement='                code="read_only_managed_field_muted",',
        wants=("test_read_only_must_not_declare_managed_field",),
        requirement="8.5",
    ),
    Case(
        id="M9-oo-only-allows-projection-fields",
        file=MAP,
        anchor=r"^        if manifest\.fields:$",
        replacement="        if False:",
        wants=("test_onlyoffice_only_must_not_create_empty_grid_peer",),
        requirement="8.6",
    ),
    Case(
        id="M10-adapter-spi-completeness-not-checked",
        file=MAP,
        anchor=r"^    return \{m for m in required if not callable\(getattr\(adapter, m, None\)\)\}$",
        replacement="    return set()",
        wants=("test_editable_grid_rejects_partial_adapter",),
        requirement="8.4",
    ),
    Case(
        id="M11-dynamic-region-skips-row-identity",
        file=MAP,
        anchor=r"^        if _has_managed_dynamic_region\(manifest\) and manifest\.row_identity is None:$",
        replacement="        if False:",
        wants=("test_dynamic_managed_region_requires_row_identity",),
        requirement="8.4",
    ),
    Case(
        id="M12-downgrade-keeps-managed-fields",
        file=MAP,
        anchor=r"^            replace_field_unmanaged\(f\) for f in confirmation\.fields$",
        replacement="            f for f in confirmation.fields",
        wants=("test_included_editable_without_carrier_downgrades_and_drops_managed",),
        requirement="8.3",
    ),
    # ── adapters ──
    Case(
        id="M13-extract-exposes-unmanaged-fields",
        file=ADAPT,
        anchor=r"^        managed = \{k: v for k, v in model\[.managed.\]\.items\(\) if k in managed_ids\}$",
        replacement="        managed = dict(model['managed'])",
        wants=("test_extract_only_exposes_managed_fields",),
        requirement="8.4",
    ),
    Case(
        id="M14-apply-accepts-unmanaged-mutation",
        file=ADAPT,
        anchor=r'^                errors\.append\(f"apply_rejects_unmanaged:\{mut\.field_id\}"\)$',
        replacement='                new_managed[mut.field_id] = mut.value  # mutate: accept unmanaged',
        wants=("test_apply_rejects_unmanaged_field_mutation",),
        requirement="8.4",
    ),
    Case(
        id="M15-merge-same-field-lww",
        file=ADAPT,
        anchor=r"^            if curr_changed and inc_changed and c != i:$",
        replacement="            if False:",
        wants=("test_merge_same_field_conflict_is_visible_not_lww",),
        requirement="8.4",
    ),
    Case(
        id="M16-merge-different-fields-drops-incoming",
        file=ADAPT,
        anchor=r"^            elif inc_changed:$",
        replacement="            elif False:",
        wants=("test_merge_different_fields_auto_merges",),
        requirement="8.4",
    ),
    Case(
        id="M17-diff-ignores-lost-unmanaged",
        file=ADAPT,
        anchor=r"^            if k not in after_unmanaged or a\[.unmanaged.\]\.get\(k\) != b\[.unmanaged.\]\[k\]$",
        replacement="            if False",
        wants=("test_diff_detects_lost_unmanaged_part",),
        requirement="8.4",
    ),
]


def _count(text: str, pattern: str) -> int:
    return len(re.findall(pattern, text, re.MULTILINE))


def check_anchors() -> int:
    bad = 0
    for case in CASES:
        n = _count(case.file.read_text(encoding="utf-8"), case.anchor)
        status = "OK" if n == 1 else "ANCHOR-MISS"
        print(f"  [{status}] {case.id} (n={n})")
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
        if not hit:
            return f"{case.id}: WRONG-TEST FAIL -- expected {case.wants}"
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
        print("FAIL baseline (must be green before mutating)")
        print(out.decode("utf-8", errors="replace")[-2000:])
        return 1
    print("OK baseline green\n")
    bad = 0
    for case in CASES:
        result = apply_one(case)
        print(f"  {result}")
        if "FAIL" in result or "ANCHOR-MISS" in result:
            bad += 1
    print(f"\nbad={bad}/{len(CASES)}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
