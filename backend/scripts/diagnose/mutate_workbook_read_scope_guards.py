"""一次性变异反证：workbook_read_scope 的两条不变量各自可被打红。

用完即删（`_` 前缀）。用法（仓库根）：
    .venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_workbook_read_scope_guards.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
TARGET = BACKEND / "app" / "services" / "workpaper_sync" / "excel_extract.py"
TEST = "tests/workpaper_sync/test_excel_extract_workbook_read_scope.py"
PY = BACKEND.parent / ".venv" / "Scripts" / "python.exe"

MUTATIONS: list[tuple[str, str, str]] = [
    (
        "去掉缓存命中（每次都重新解析）",
        "    hit = cache.get(key)\n    if hit is None:",
        "    hit = None\n    if hit is None:",
    ),
    (
        "去掉作用域退出时的 close（句柄泄漏）",
        "        for workbook in cache.values():\n"
        "            try:\n"
        "                workbook.close()",
        "        for workbook in cache.values():\n"
        "            try:\n"
        "                pass  # MUTATED: 不关闭",
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
    rc, out = run_tests()
    tail = [l for l in out.splitlines() if "passed" in l or "failed" in l]
    print(f"[baseline] rc={rc}  {tail[-1] if tail else out[-200:]}")
    if rc != 0:
        print("基线不绿，终止")
        return 1

    # 锚点按**盘上真实行尾**归一化：本仓 core.autocrlf=true，源文件 checkout 后是 CRLF，
    # 用 \n 写的锚点会整条 MISS（test_guidance_gc0_conformance 记录过同一个坑）。
    eol = "\r\n" if b"\r\n" in original else "\n"
    print(f"[eol] 盘上行尾 = {eol!r}")

    failures = 0
    try:
        for label, old_lf, new_lf in MUTATIONS:
            old = old_lf.replace("\n", eol)
            new = new_lf.replace("\n", eol)
            text = original.decode("utf-8")
            if old not in text:
                print(f"[MISS] 锚点没命中：{label}")
                failures += 1
                continue
            assert text.count(old) == 1, f"锚点不唯一：{label}"
            TARGET.write_bytes(text.replace(old, new, 1).encode("utf-8"))
            rc, out = run_tests()
            red = [l for l in out.splitlines() if "FAILED" in l or "failed" in l]
            status = "KILLED" if rc != 0 else "SURVIVED<<<"
            print(f"[{status}] {label}")
            for line in red[:6]:
                print(f"    {line}")
            if rc == 0:
                failures += 1
            TARGET.write_bytes(original)
    finally:
        TARGET.write_bytes(original)
        assert TARGET.read_bytes() == original, "还原失败！"
        print("[restore] 字节已逐字节还原")

    rc, out = run_tests()
    tail = [l for l in out.splitlines() if "passed" in l or "failed" in l]
    print(f"[post-restore] rc={rc}  {tail[-1] if tail else ''}")
    return 1 if failures or rc != 0 else 0


if __name__ == "__main__":
    sys.exit(main())
