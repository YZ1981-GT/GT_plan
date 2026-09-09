"""Task 9 变异检验 harness。

🔴 每条锚点必须让对应测试 RED。

用法：
    python backend/scripts/diagnose/mutate_guidance_api_task9_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_guidance_api_task9_guards.py
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_FILE = REPO_ROOT / "backend/app/services/guidance_api_contract.py"
SVC_FILE = REPO_ROOT / "backend/app/services/wp_guidance_service.py"
TEST_TARGET = "backend/tests/test_guidance_api_task9.py"


MUTATIONS = [
    # AC#1: fingerprint 常量 → 所有 response 同一 ETag，缓存永远命中
    (
        "M-T9-FINGERPRINT-CONST",
        CONTRACT_FILE,
        "    canonical = json.dumps(parts, sort_keys=True, separators=(\",\", \":\"), ensure_ascii=False, default=str)\n"
        "    return hashlib.sha256(canonical.encode(\"utf-8\")).hexdigest()",
        "    return \"0\" * 64  # BUG: 常量",
        "test_response_has_schema_contract_response_versions",
    ),
    # AC#2: cache key 去掉 schema_version → schema 变不 invalidate
    (
        "M-T9-CACHE-KEY-NO-SCHEMA",
        CONTRACT_FILE,
        "        \"schema_version\": schema_version,",
        "        \"schema_version\": None,  # BUG",
        "test_stable_cache_key_changes_when_schema_changes",
    ),
    # AC#4: gate 只验 epoch 忽略 revision → 旧 revision 响应落地
    (
        "M-T9-GATE-NO-REVISION",
        CONTRACT_FILE,
        "        if self.revision is not None and incoming_revision != self.revision:\n"
        "            return False",
        "        if False and self.revision is not None and incoming_revision != self.revision:\n"
        "            return False",
        "test_rejects_mismatched_revision",
    ),
    # AC#6: 结构化错误被吞掉 → invalid/stale 状态不返 error
    (
        "M-T9-ERROR-NOP",
        SVC_FILE,
        "        if resolution_status in {\"invalid\", \"stale\", \"missing\", \"blocked\"}:",
        "        if False and resolution_status in {\"invalid\", \"stale\", \"missing\", \"blocked\"}:",
        "test_stale_status_yields_structured_error",
    ),
    # AC#1: etag 常量 → 所有 response 同一 etag
    (
        "M-T9-ETAG-CONST",
        CONTRACT_FILE,
        "    return f'W/\"{response_version}\"'",
        "    return 'W/\"fixed\"'  # BUG",
        "test_etag_is_weak_format",
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
