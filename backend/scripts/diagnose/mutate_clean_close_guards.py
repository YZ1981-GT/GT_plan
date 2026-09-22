"""变异反证：未改动 clean close 的四条判据可被打红（含 dirty 硬门这条数据安全）。

用法（仓库根）：
    .venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_clean_close_guards.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FRONTEND = REPO / "audit-platform" / "frontend"
SYNC = FRONTEND / "src" / "components" / "workpaper" / "sync"
BRIDGE = SYNC / "useWorkpaperSyncBridge.ts"
MACHINE = SYNC / "workpaperSyncBridgeMachine.ts"
TEST = "src/components/workpaper/sync/__tests__/cleanCloseWithoutSaving.spec.ts"

MUTATIONS: list[tuple[str, Path, str, str]] = [
    (
        "去掉离开阻断门（dirty 时会静默丢弃未保存编辑）",
        BRIDGE,
        "    if (!canLeave.value) {\n"
        "      refuse(\n"
        "        dirty.value",
        "    if (false) {\n"
        "      refuse(\n"
        "        dirty.value",
    ),
    (
        "clean close 又去发 close-intent（实测会把 room 锁在 close_barrier）",
        BRIDGE,
        "    apply('clean_close_completed')\n"
        "    descriptor.value = null",
        "    await api.createCloseIntent(scope(), {\n"
        "      roomId: String(descriptor.value?.roomId ?? ''),\n"
        "      participantId: String(descriptor.value?.participantId ?? ''),\n"
        "    })\n"
        "    apply('clean_close_completed')\n"
        "    descriptor.value = null",
    ),
    (
        "离开后不清 descriptor（留一个指向已离开 room 的 descriptor）",
        BRIDGE,
        "    apply('clean_close_completed')\n"
        "    descriptor.value = null\n"
        "    confirmation.value = null",
        "    apply('clean_close_completed')\n"
        "    confirmation.value = null",
    ),
    (
        "把 clean_close_completed 也开给保存进行中的状态",
        MACHINE,
        "    forcesave_requesting: {\n"
        "      forcesave_dispatch_failed: 'forcesave_frozen',",
        "    forcesave_requesting: {\n"
        "      clean_close_completed: 'html_idle',\n"
        "      forcesave_dispatch_failed: 'forcesave_frozen',",
    ),
]


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
    return out[-140:].replace("\n", " ")


def main() -> int:
    originals = {path: path.read_bytes() for path in {BRIDGE, MACHINE}}
    rc, out = run_tests()
    print(f"[baseline] rc={rc}  {summary(out)}")
    if rc != 0:
        print("基线不绿，终止")
        return 1

    failures = 0
    try:
        for label, target, old_lf, new_lf in MUTATIONS:
            original = originals[target]
            eol = "\r\n" if b"\r\n" in original else "\n"
            old = old_lf.replace("\n", eol)
            new = new_lf.replace("\n", eol)
            text = original.decode("utf-8")
            hits = text.count(old)
            if hits != 1:
                print(f"[MISS] 锚点命中 {hits} 次（需 1）：{label}")
                failures += 1
                continue
            target.write_bytes(text.replace(old, new, 1).encode("utf-8"))
            rc, out = run_tests()
            print(f"[{'KILLED' if rc != 0 else 'SURVIVED<<<'}] {label}")
            print(f"    {summary(out)}")
            if rc == 0:
                failures += 1
            target.write_bytes(original)
    finally:
        for path, raw in originals.items():
            path.write_bytes(raw)
            assert path.read_bytes() == raw, f"还原失败：{path}"
        print("[restore] 已逐字节还原")

    rc, out = run_tests()
    print(f"[post-restore] rc={rc}  {summary(out)}")
    return 1 if failures or rc != 0 else 0


if __name__ == "__main__":
    sys.exit(main())
