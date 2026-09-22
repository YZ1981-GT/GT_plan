"""一次性变异反证：指纹记忆化的三条不变量各自可被打红。

用完即删（`_` 前缀）。用法（仓库根）：
    .venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_fingerprint_memoization_guards.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
TARGET = BACKEND / "app" / "services" / "excel_structure_fingerprint.py"
TEST = "tests/test_structure_fingerprint_memoization.py"
PY = BACKEND.parent / ".venv" / "Scripts" / "python.exe"

MUTATIONS: list[tuple[str, str, str]] = [
    (
        "去掉缓存命中（每次都重新解析）",
        "    cached = _FINGERPRINT_CACHE.get(key)\n    if cached is not None:",
        "    cached = None\n    if cached is not None:",
    ),
    (
        "命中时不 deepcopy（把缓存对象原样交出去）",
        "        _FINGERPRINT_CACHE.move_to_end(key)\n        return copy.deepcopy(cached)",
        "        _FINGERPRINT_CACHE.move_to_end(key)\n        return cached",
    ),
    (
        "存入时不 deepcopy（首次返回值与缓存同一对象）",
        "    _FINGERPRINT_CACHE[key] = copy.deepcopy(computed)",
        "    _FINGERPRINT_CACHE[key] = computed",
    ),
    (
        "去掉 LRU 淘汰（无界增长）",
        "    while len(_FINGERPRINT_CACHE) > _FINGERPRINT_CACHE_MAX:\n"
        "        _FINGERPRINT_CACHE.popitem(last=False)",
        "    while False:\n        _FINGERPRINT_CACHE.popitem(last=False)",
    ),
    (
        "缓存键改成长度（不同字节会串）",
        "    key = _sha256(data)\n    cached = _FINGERPRINT_CACHE.get(key)",
        "    key = str(len(data))\n    cached = _FINGERPRINT_CACHE.get(key)",
    ),
]


def run_tests() -> tuple[int, str]:
    proc = subprocess.run(
        [str(PY), "-m", "pytest", TEST, "-q", "--tb=line", "-p", "no:randomly"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def main() -> int:
    original = TARGET.read_bytes()
    eol = "\r\n" if b"\r\n" in original else "\n"
    rc, out = run_tests()
    tail = [line for line in out.splitlines() if "passed" in line or "failed" in line]
    print(f"[baseline] rc={rc}  {tail[-1] if tail else out[-200:]}")
    if rc != 0:
        print("基线不绿，终止")
        return 1

    failures = 0
    try:
        for label, old_lf, new_lf in MUTATIONS:
            old = old_lf.replace("\n", eol)
            new = new_lf.replace("\n", eol)
            text = original.decode("utf-8")
            hits = text.count(old)
            if hits != 1:
                print(f"[MISS] 锚点命中 {hits} 次（需 1）：{label}")
                failures += 1
                continue
            TARGET.write_bytes(text.replace(old, new, 1).encode("utf-8"))
            rc, out = run_tests()
            red = [line for line in out.splitlines() if "FAILED" in line]
            summary = [
                line for line in out.splitlines() if "passed" in line or "failed" in line
            ]
            print(f"[{'KILLED' if rc != 0 else 'SURVIVED<<<'}] {label}")
            print(f"    {summary[-1] if summary else ''}")
            for line in red[:3]:
                print(f"    {line}")
            if rc == 0:
                failures += 1
            TARGET.write_bytes(original)
    finally:
        TARGET.write_bytes(original)
        assert TARGET.read_bytes() == original, "还原失败！"
        print("[restore] 已逐字节还原")

    rc, out = run_tests()
    tail = [line for line in out.splitlines() if "passed" in line or "failed" in line]
    print(f"[post-restore] rc={rc}  {tail[-1] if tail else ''}")
    return 1 if failures or rc != 0 else 0


if __name__ == "__main__":
    sys.exit(main())
