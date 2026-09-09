"""Guidance Publication 服务层的变异检验 harness。

🔴 每个锚点必须让对应测试 RED（不是 ANCHOR-MISS / GREEN）。
判据见 memory.md「假绿三源」——字符串存在型守卫不算数，必须是行为型。

用法：
    python backend/scripts/diagnose/mutate_guidance_publication_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_guidance_publication_guards.py
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SVC_FILE = REPO_ROOT / "backend/app/services/guidance_publication_service.py"
TEST_TARGET = "backend/tests/test_guidance_publication_lifecycle.py"


# 每条变异：(id, 文件, 旧片段, 新片段, 期望失败的测试关键字)
MUTATIONS = [
    (
        "M-IMM-NOP",
        SVC_FILE,
        "    if pub.status == PUBLICATION_PUBLISHED:\n        raise GuidanceImmutableError(",
        "    if False and pub.status == PUBLICATION_PUBLISHED:\n        raise GuidanceImmutableError(",
        "test_mutable_rejects_published",
    ),
    (
        "M-AUTH-REMOVED",
        SVC_FILE,
        "    if actor == reviewer:\n        raise GuidanceForbiddenError(",
        "    if False and actor == reviewer:\n        raise GuidanceForbiddenError(",
        "test_rejects_self_review",
    ),
    (
        "M-DIGEST-CONSTANT",
        SVC_FILE,
        "    return hashlib.sha256(canonical.encode(\"utf-8\")).hexdigest()",
        "    return \"0\" * 64",
        "test_content_digest_decoupled_from_source_digest",
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
        raise SystemExit(f"ANCHOR-MISS {mid}: ambiguous (multiple matches) in {path.name}")


def _apply(path: Path, old: str, new: str) -> bytes:
    """返回原始 bytes（用于精确还原）。"""
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


def _run_pytest(expect_fail_keyword: str) -> tuple[int, str]:
    cmd = [
        sys.executable, "-m", "pytest", TEST_TARGET,
        "-q", "--tb=line", "-p", "no:cacheprovider",
        "-k", expect_fail_keyword,
    ]
    proc = subprocess.run(
        cmd, cwd=str(REPO_ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    return proc.returncode, (proc.stdout + proc.stderr)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-anchors", action="store_true",
                        help="仅校验锚点可命中，不做变异")
    args = parser.parse_args()

    if args.check_anchors:
        print("=== check anchors ===")
        for mid, path, old, new, _kw in MUTATIONS:
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
            rc, out = _run_pytest(kw)
            # 期望变异后测试失败（rc != 0）
            if rc == 0:
                print(f"  🔴 GREEN {mid}: mutation did NOT fail any test — GUARD DEFECT")
                any_green = True
            else:
                print(f"  ✅ RED   {mid}: expected failure detected")
        finally:
            _restore(path, original)
        assert _read_bytes(path) == original, f"{mid}: restore failed"

    if any_green:
        print("\n🔴 AT LEAST ONE GUARD DEFECT — fix or the mutations would be invisible")
        return 2
    print("\n✅ all mutations hit RED — guards are alive")
    return 0


if __name__ == "__main__":
    sys.exit(main())
