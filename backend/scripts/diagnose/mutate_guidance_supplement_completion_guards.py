"""Supplement / Exemption / Completion 服务的变异检验 harness。

🔴 覆盖 Task 6 剩余 AC：
    * supplement runtime subject 绑定
    * supplement evidence 非空
    * canonical section presence 只读 published+active
    * status_ok 判据（published + active）

用法：
    python backend/scripts/diagnose/mutate_guidance_supplement_completion_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_guidance_supplement_completion_guards.py
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SVC_SUP = REPO_ROOT / "backend/app/services/project_guidance_supplement_service.py"
SVC_EX = REPO_ROOT / "backend/app/services/guidance_exemption_service.py"
SVC_COMP = REPO_ROOT / "backend/app/services/guidance_completion_guard.py"
TEST_TARGET = "backend/tests/test_guidance_publication_lifecycle.py"


MUTATIONS = [
    (
        "M-SUP-SUBJECT-NOP",
        SVC_SUP,
        "    if project_id is None:\n        raise SupplementPublicError(",
        "    if False and project_id is None:\n        raise SupplementPublicError(",
        "test_rejects_missing_project_id",
    ),
    (
        "M-SUP-EVID-NOP",
        SVC_SUP,
        "    if not project_evidence_json:\n        raise SupplementPublicError(",
        "    if False and not project_evidence_json:\n        raise SupplementPublicError(",
        "test_rejects_empty_evidence",
    ),
    (
        "M-EX-OWNER-NOP",
        SVC_EX,
        "    if owner_user_id == approver_user_id:\n        raise GuidanceForbiddenError(",
        "    if False and owner_user_id == approver_user_id:\n        raise GuidanceForbiddenError(",
        "test_rejects_same_user",
    ),
    (
        "M-EX-EXPIRY-NOP",
        SVC_EX,
        "    if expires_at is None:\n        raise ExemptionPublicError(",
        "    if False and expires_at is None:\n        raise ExemptionPublicError(",
        "test_rejects_none_expiry",
    ),
    (
        "M-COMP-STATUS",
        SVC_COMP,
        "    if pub.status != PUBLICATION_PUBLISHED:\n        return False",
        "    if False and pub.status != PUBLICATION_PUBLISHED:\n        return False",
        "test_status_ok_requires_published_and_active",
    ),
    (
        "M-COMP-EXEMPT",
        SVC_COMP,
        "    return not (missing - set(exempt_sections))",
        "    return not missing  # BUG: 豁免被忽略",
        "test_exemption_allows_partial_completion_but_not_supplement_fill",
    ),
]


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _write_bytes(path: Path, data: bytes) -> None:
    path.write_bytes(data)


def _assert_anchor(path: Path, old: str, mid: str) -> None:
    payload = _read_bytes(path)
    if old.encode("utf-8") not in payload:
        raise SystemExit(f"ANCHOR-MISS {mid}: old fragment not found in {path.name}")
    if payload.count(old.encode("utf-8")) != 1:
        raise SystemExit(f"ANCHOR-MISS {mid}: ambiguous in {path.name}")


def _apply(path: Path, old: str, new: str) -> bytes:
    payload = _read_bytes(path)
    eol = b"\r\n" if payload.count(b"\r\n") else b"\n"
    old_b = old.encode("utf-8")
    if old_b not in payload:
        raise SystemExit(f"anchor missing: {old!r}")
    new_b = new.encode("utf-8").replace(b"\n", eol)
    mutated = payload.replace(old_b, new_b, 1)
    _write_bytes(path, mutated)
    return payload


def _restore(path: Path, original: bytes) -> None:
    _write_bytes(path, original)


def _run_pytest(expect_fail_keyword: str) -> int:
    cmd = [
        sys.executable, "-m", "pytest", TEST_TARGET,
        "-q", "--tb=line", "-p", "no:cacheprovider",
        "-k", expect_fail_keyword,
    ]
    proc = subprocess.run(
        cmd, cwd=str(REPO_ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-anchors", action="store_true")
    args = parser.parse_args()

    if args.check_anchors:
        print("=== check anchors ===")
        for mid, path, old, _n, _kw in MUTATIONS:
            _assert_anchor(path, old, mid)
            print(f"  OK {mid}: anchor found in {path.name}")
        return 0

    print("=== running mutations ===")
    any_green = False
    for mid, path, old, new, kw in MUTATIONS:
        _assert_anchor(path, old, mid)
        original = _read_bytes(path)
        try:
            _apply(path, old, new)
            rc = _run_pytest(kw)
            if rc == 0:
                print(f"  🔴 GREEN {mid}: mutation did NOT fail any test — GUARD DEFECT")
                any_green = True
            else:
                print(f"  ✅ RED   {mid}: expected failure detected")
        finally:
            _restore(path, original)
        assert _read_bytes(path) == original, f"{mid}: restore failed"

    if any_green:
        print("\n🔴 AT LEAST ONE GUARD DEFECT")
        return 2
    print("\n✅ all mutations hit RED — guards are alive")
    return 0


if __name__ == "__main__":
    sys.exit(main())
