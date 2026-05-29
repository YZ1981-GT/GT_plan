"""热点文件 pull 检测（pre-commit hook）。

repo-git-workflow-unification spec / Sprint 1 / Task 1.3

逻辑：
- staged 文件含 git_hotspot_files.txt 中的项 + 本地 behind > 0 即拒
- single 模式（GIT_MODE=single 或未设）跳过（仅警告不阻断）
- multi 模式（GIT_MODE=multi）阻断 commit

用法：
    python backend/scripts/check_hotspot_files.py file1 file2 ...
    （pre-commit 自动传 staged 文件）

退出码：
    0 = 通过
    1 = 阻断（multi 模式 + 命中热点 + behind > 0）
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOTSPOT_LIST = ROOT / "backend" / "scripts" / "git_hotspot_files.txt"


def load_hotspot_files() -> set[str]:
    if not HOTSPOT_LIST.exists():
        return set()
    return {
        line.strip()
        for line in HOTSPOT_LIST.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


def get_git_mode() -> str:
    return os.environ.get("GIT_MODE", "single").lower()


def get_behind_count() -> int:
    try:
        branch_result = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            capture_output=True, text=True, encoding="utf-8", timeout=10,
        )
        branch = branch_result.stdout.strip()
        if not branch:
            return 0
        result = subprocess.run(
            ["git", "rev-list", "--count", f"HEAD..origin/{branch}"],
            capture_output=True, text=True, encoding="utf-8", timeout=10,
        )
        s = result.stdout.strip()
        return int(s) if s.isdigit() else 0
    except Exception:
        return 0


def normalize(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def main() -> int:
    files = sys.argv[1:]
    if not files:
        return 0

    hotspot = load_hotspot_files()
    if not hotspot:
        return 0

    mode = get_git_mode()
    has_hotspot = [f for f in files if normalize(f) in hotspot]
    if not has_hotspot:
        return 0

    behind = get_behind_count()
    if behind == 0:
        return 0  # 已最新，安全

    msg = (
        f"❌ 检测到热点文件改动 + 本地 behind 远程 {behind} commit:\n"
        + "\n".join(f"   - {f}" for f in has_hotspot)
        + "\n\n"
        + "   建议先 `git pull --rebase origin <branch>` 再 commit\n"
        + "   避免覆盖他人改动（INDEX.md / memory.md 等高频冲突文件）"
    )

    if mode == "multi":
        print(msg, file=sys.stderr)
        print(f"   GIT_MODE=multi → 阻断 commit", file=sys.stderr)
        return 1
    else:
        # single 模式仅警告
        print(msg, file=sys.stderr)
        print(f"   GIT_MODE={mode} → 仅警告，未阻断", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
