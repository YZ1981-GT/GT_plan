"""一次性变异反证：把 forcesave_frozen 从 canForcesave 放行集合里拿掉必须打红。

用完即删（`_` 前缀）。用法（仓库根）：
    .venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_forcesave_frozen_retry_guards.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TARGET = (
    REPO
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "sync"
    / "useWorkpaperSyncBridge.ts"
)
FRONTEND = REPO / "audit-platform" / "frontend"
TEST = "src/components/workpaper/sync/__tests__/forcesaveFrozenRetryable.spec.ts"


def run_tests() -> tuple[int, str]:
    proc = subprocess.run(
        ["npx", "vitest", "run", TEST, "--reporter=basic"],
        cwd=FRONTEND,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=True,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def summary(out: str) -> str:
    for line in out.splitlines():
        if "Tests " in line and ("passed" in line or "failed" in line):
            return line.strip()
    return out[-160:].replace("\n", " ")


def main() -> int:
    original = TARGET.read_bytes()
    eol = "\r\n" if b"\r\n" in original else "\n"
    text = original.decode("utf-8")

    old = (
        "export const WP_BRIDGE_FORCESAVE_READY_STATES: "
        "readonly WorkpaperSyncBridgeState[] = [" + eol
        + "  'oo_editing'," + eol
        + "  'forcesave_frozen'," + eol
        + "]"
    )
    if text.count(old) != 1:
        print(f"[MISS] 锚点命中 {text.count(old)} 次（需 1）")
        return 1
    new = (
        "export const WP_BRIDGE_FORCESAVE_READY_STATES: "
        "readonly WorkpaperSyncBridgeState[] = [" + eol
        + "  'oo_editing'," + eol
        + "]"
    )

    rc, out = run_tests()
    print(f"[baseline] rc={rc}  {summary(out)}")
    if rc != 0:
        print("基线不绿，终止")
        return 1

    try:
        TARGET.write_bytes(text.replace(old, new, 1).encode("utf-8"))
        rc, out = run_tests()
        killed = rc != 0
        print(f"[{'KILLED' if killed else 'SURVIVED<<<'}] 去掉 forcesave_frozen 放行")
        print(f"    {summary(out)}")
        for line in out.splitlines():
            if "提示语在骗用户" in line or "canForcesave" in line:
                print(f"    {line.strip()[:150]}")
                break
    finally:
        TARGET.write_bytes(original)
        assert TARGET.read_bytes() == original, "还原失败！"
        print("[restore] 已逐字节还原")

    rc, out = run_tests()
    print(f"[post-restore] rc={rc}  {summary(out)}")
    return 0 if killed and rc == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
