"""Task 8 resolve_authoritative_exact 的变异检验 harness。

🔴 每条锚点必须让对应测试 RED，否则视为守卫缺陷。

用法：
    python backend/scripts/diagnose/mutate_guidance_resolution_task8_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_guidance_resolution_task8_guards.py
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SVC_FILE = REPO_ROOT / "backend/app/services/wp_guidance_service.py"
TEST_TARGET = "backend/tests/test_guidance_resolution_task8.py"


MUTATIONS = [
    # AC#1：删掉 membership 校验 → 跨 wp/sheet 不再 403
    (
        "M-T8-MEMBERSHIP-NOP",
        SVC_FILE,
        "        if requested is not None and requested != parent_wp_code:\n"
        "            self._assert_sheet_membership(",
        "        if False and requested is not None and requested != parent_wp_code:\n"
        "            self._assert_sheet_membership(",
        "test_resolve_raises_on_cross_wp_membership",
    ),
    # AC#1：删掉 authority_sheet_codes 判定
    (
        "M-T8-MEMBERSHIP-LIST-NOP",
        SVC_FILE,
        "        if authority_sheet_codes is not None and requested_sheet_code not in authority_sheet_codes:",
        "        if False and authority_sheet_codes is not None and requested_sheet_code not in authority_sheet_codes:",
        "test_rejects_sheet_not_in_authority",
    ),
    # AC#1：删掉 runtime_wp 匹配 → 跨 wp entry 泄漏
    (
        "M-T8-MEMBERSHIP-RUNTIME-NOP",
        SVC_FILE,
        "        if runtime_wp and runtime_wp != authority_wp_code:",
        "        if False and runtime_wp and runtime_wp != authority_wp_code:",
        "test_rejects_runtime_entry_wp_mismatch",
    ),
    # AC#6：删掉 contractVersion/schemaVersion 输出 → Response 缺字段
    (
        "M-T8-CONTRACT-NOP",
        SVC_FILE,
        "            \"contractVersion\": GUIDANCE_CONTRACT_VERSION,",
        "            \"contractVersion\": None,",
        "test_response_has_contract_and_schema_version",
    ),
    # AC#6：删掉 provenance 输出
    (
        "M-T8-PROVENANCE-NOP",
        SVC_FILE,
        "            \"provenance\": provenance.to_dict() if provenance else {",
        "            \"provenance\": {},  # BUG",
        "test_response_has_provenance_structure",
    ),
]


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _write_bytes(path: Path, data: bytes) -> None:
    path.write_bytes(data)


def _assert_anchor(path: Path, old: str, mid: str) -> None:
    payload = _read_bytes(path)
    eol = b"\r\n" if payload.count(b"\r\n") else b"\n"
    old_b = old.encode("utf-8").replace(b"\n", eol)
    if old_b not in payload:
        raise SystemExit(f"ANCHOR-MISS {mid}: fragment not found in {path.name}")
    if payload.count(old_b) != 1:
        raise SystemExit(f"ANCHOR-MISS {mid}: ambiguous in {path.name}")


def _apply(path: Path, old: str, new: str) -> bytes:
    payload = _read_bytes(path)
    eol = b"\r\n" if payload.count(b"\r\n") else b"\n"
    old_b = old.encode("utf-8").replace(b"\n", eol)
    new_b = new.encode("utf-8").replace(b"\n", eol)
    if old_b not in payload:
        raise SystemExit(f"anchor missing: {old!r}")
    mutated = payload.replace(old_b, new_b, 1)
    _write_bytes(path, mutated)
    return payload


def _restore(path: Path, original: bytes) -> None:
    _write_bytes(path, original)


def _run_pytest(kw: str) -> int:
    cmd = [
        sys.executable, "-m", "pytest", TEST_TARGET,
        "-q", "--tb=line", "-p", "no:cacheprovider",
        "-k", kw,
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
            print(f"  OK {mid}: anchor found")
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
                print(f"  🔴 GREEN {mid}: GUARD DEFECT")
                any_green = True
            else:
                print(f"  ✅ RED   {mid}: expected failure")
        finally:
            _restore(path, original)
        assert _read_bytes(path) == original, f"{mid}: restore failed"

    if any_green:
        print("\n🔴 AT LEAST ONE GUARD DEFECT")
        return 2
    print("\n✅ all mutations hit RED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
