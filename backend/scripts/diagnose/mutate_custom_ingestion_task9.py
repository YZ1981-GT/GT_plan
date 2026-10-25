"""Task 9 变异：破坏 candidate 静态预览 / candidate guidance 关键裁决点。

用法:
  python backend/scripts/diagnose/mutate_custom_ingestion_task9.py --check-anchors
  python backend/scripts/diagnose/mutate_custom_ingestion_task9.py --apply

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
PREVIEW = BASE / "candidate_preview.py"
GUIDE = BASE / "candidate_guidance.py"

PYTEST_ARGS = [
    sys.executable, "-m", "pytest",
    "tests/custom_template_ingestion/test_candidate_preview.py",
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
    # ── sanitizer (9.2) ──
    Case(
        id="P1-sanitizer-passthrough-no-escape",
        file=PREVIEW,
        anchor=r"^    return html\.escape\(text, quote=True\)$",
        replacement="    return text  # mutate: no escape",
        wants=(
            "test_sanitizer_escapes_and_never_yields_executable_sink",
            "test_static_html_surface_contains_no_executable_markup",
        ),
        requirement="9.2",
    ),
    # ── static-only surface kinds closed (9.1) ──
    Case(
        id="P2-preview-surface-kind-set-widened",
        file=PREVIEW,
        anchor=r"^    NONEXECUTABLE_IMAGE = \"nonexecutable_image\"$",
        replacement='    NONEXECUTABLE_IMAGE = "nonexecutable_image"\n    ONLYOFFICE_CONFIG = "onlyoffice_config"',
        wants=("test_preview_surface_kinds_are_closed_to_static_only",),
        requirement="9.1",
    ),
    # ── forbidden production sink appears in real code path (9.1 structural) ──
    Case(
        id="P3-production-oo-sink-introduced",
        file=PREVIEW,
        anchor=r'^        \"encoding\": \"server_rasterized_bitmap\",$',
        replacement='        "encoding": "server_rasterized_bitmap",\n        "documentserver": "http://oo/wopi",',
        wants=("test_module_source_has_no_production_oo_wopi_sink",),
        requirement="9.1",
    ),
    # ── token fingerprint match (9.5) ──
    Case(
        id="P4-token-fingerprint-always-valid",
        file=PREVIEW,
        anchor=r"^        return self\.bound_fingerprint == _candidate_fingerprint\(candidate\)$",
        replacement="        return True  # mutate: ignore digest",
        wants=(
            "test_guidance_digest_change_makes_preview_stale",
            "test_any_input_digest_change_makes_preview_stale",
            "test_token_bound_to_specific_candidate_id",
        ),
        requirement="9.5",
    ),
    # ── fingerprint drops a specific input digest (9.5) ──
    Case(
        id="P5-fingerprint-drops-mapping-digest",
        file=PREVIEW,
        anchor=r'^            \"mapping\": candidate\.mapping_digest,$',
        replacement='            "mapping": "STATIC",',
        wants=("test_any_input_digest_change_makes_preview_stale",),
        requirement="9.5",
    ),
    # ── token active/pending gate (9.6) ──
    Case(
        id="P6-token-ignores-non-previewable-state",
        file=PREVIEW,
        anchor=r"^        if not candidate_active_or_pending:\n            return False$",
        replacement="        if False:\n            return False",
        wants=("test_token_invalid_when_candidate_not_active_or_pending",),
        requirement="9.6",
    ),
    # ── build_preview refuses non-previewable candidate (9.6) ──
    Case(
        id="P7-build-preview-allows-non-previewable",
        file=PREVIEW,
        anchor=r"^        if not candidate_active_or_pending:\n            raise PreviewError\($",
        replacement="        if False:\n            raise PreviewError(",
        wants=("test_non_previewable_candidate_blocks_preview_generation",),
        requirement="9.6",
    ),
    # ── expired token (9.5/9.6) ──
    Case(
        id="P8-token-never-expires",
        file=PREVIEW,
        anchor=r"^        return clock\.now\(\) >= self\.expires_at$",
        replacement="        return False  # mutate: never expires",
        wants=("test_expired_token_is_stale",),
        requirement="9.5",
    ),
    # ── guidance: candidate phase gate (9.4) ──
    Case(
        id="G1-guidance-accepts-non-candidate-phase",
        file=GUIDE,
        anchor=r"^    if phase != candidate_variant:$",
        replacement="    if False:",
        wants=("test_guidance_preview_rejects_finalized_phase_even_without_finalized_fields",),
        requirement="9.4",
    ),
    # ── guidance: authority phase gate (9.4) ──
    Case(
        id="G2-guidance-ignores-authority-phase",
        file=GUIDE,
        anchor=r'^    if authority\.get\("phase"\) != candidate_variant:$',
        replacement="    if False and authority.get(\"phase\") != candidate_variant:",
        wants=("test_guidance_preview_rejects_finalized_authority_phase_only",),
        requirement="9.4",
    ),
    # ── guidance: finalized-only field top-level rejection (9.4) ──
    Case(
        id="G3-guidance-allows-toplevel-finalization-field",
        file=GUIDE,
        anchor=r"^        if fld in handoff:$",
        replacement="        if False:",
        wants=("test_guidance_preview_rejects_candidate_with_forged_finalization_field",),
        requirement="9.4",
    ),
    # ── guidance: finalized-only field authority rejection (9.4) ──
    Case(
        id="G4-guidance-allows-authority-finalization-field",
        file=GUIDE,
        anchor=r"^        if fld in authority:$",
        replacement="        if False:",
        wants=("test_guidance_preview_rejects_authority_forged_finalization_field",),
        requirement="9.4",
    ),
    # ── guidance: G-C0 version gate (9.4) ──
    Case(
        id="G5-guidance-skips-gc0-version-gate",
        file=GUIDE,
        anchor=r"^    if not decision\.is_accept:$",
        replacement="    if False:",
        wants=("test_guidance_preview_rejects_bad_contract_version",),
        requirement="9.4",
    ),
    # ── guidance: never emits confirmed (9.4) ──
    Case(
        id="G6-guidance-emits-confirmed-true",
        file=GUIDE,
        anchor=r'^        \"confirmed\": False,$',
        replacement='        "confirmed": True,',
        wants=("test_guidance_preview_never_emits_custom_confirmed",),
        requirement="9.4",
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
