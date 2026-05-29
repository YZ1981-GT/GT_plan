"""分支命名规约检测。

repo-git-workflow-unification spec / Sprint 1 / Task 1.2

5 类合法前缀：
- main                          唯一主线
- spec/<spec-name>              spec 实施分支（必须对应 .kiro/specs/<name>/ 真实存在）
- work/YYYY-MM-DD-<topic>       单次工作分支
- fix/<issue>                   bug 热修
- release/v<version>            发布候选

用法：
    python backend/scripts/check_git_branch_naming.py <branch-name>
    python backend/scripts/check_git_branch_naming.py             # 检测当前分支

退出码：
    0 = 合法
    1 = 不合规
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PATTERNS = [
    (re.compile(r"^main$"), "main", "唯一主线"),
    (re.compile(r"^spec/([a-z0-9][a-z0-9-]*)$"), "spec", "spec 实施"),
    (re.compile(r"^work/(\d{4}-\d{2}-\d{2})-([a-z0-9-]+)$"), "work", "单次工作"),
    (re.compile(r"^fix/([a-z0-9][a-z0-9-]*)$"), "fix", "bug 热修"),
    (re.compile(r"^release/v(\d+)\.(\d+)(\.\d+)?(-[a-z0-9.-]+)?$"), "release", "发布候选"),
]


def get_current_branch() -> str:
    try:
        result = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            capture_output=True, text=True, encoding="utf-8", timeout=10,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def validate(branch: str) -> tuple[bool, str, str]:
    """返回 (合法?, 类型前缀, 错误描述)。"""
    for pat, prefix, desc in PATTERNS:
        m = pat.match(branch)
        if m:
            # spec/<name> 还要校验目录存在
            if prefix == "spec":
                spec_name = m.group(1)
                spec_dir = ROOT / ".kiro" / "specs" / spec_name
                spec_archive = ROOT / ".kiro" / "specs" / "_archive" / spec_name
                if not spec_dir.is_dir() and not spec_archive.is_dir():
                    return False, prefix, (
                        f"分支 spec/{spec_name} 但 .kiro/specs/{spec_name}/ 不存在；"
                        "先建 spec 三件套再开分支"
                    )
            return True, prefix, ""
    return False, "", (
        f"分支名 '{branch}' 不符合命名规约。\n"
        "  合法前缀:\n"
        "  - main                       (唯一主线)\n"
        "  - spec/<spec-name>           (spec 实施，必须对应 .kiro/specs/<name>/)\n"
        "  - work/YYYY-MM-DD-<topic>    (单次工作)\n"
        "  - fix/<issue>                (bug 热修)\n"
        "  - release/v<version>         (发布)"
    )


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    branch = args[0] if args else get_current_branch()
    if not branch:
        print("ERROR: 无法获取当前分支", file=sys.stderr)
        return 1

    ok, prefix, msg = validate(branch)
    if ok:
        print(f"[OK] {branch} -> {prefix}")
        return 0
    print(f"[FAIL] {branch}", file=sys.stderr)
    print(msg, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
