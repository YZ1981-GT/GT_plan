"""6 维 git 同步状态核查工具。

repo-git-workflow-unification spec / Sprint 1 / Task 1.1

6 维核查：
1. 工作树 = clean
2. 本地 HEAD == 远程 HEAD
3. ahead 数
4. behind 数
5. 未跟踪文件数
6. 最新 commit 信息

用法：
    python backend/scripts/check_git_sync_state.py              # 输出报表
    python backend/scripts/check_git_sync_state.py --for-push   # 严格模式（pre-push）
    python backend/scripts/check_git_sync_state.py --report     # markdown 表格
    python backend/scripts/check_git_sync_state.py --branch=main # 指定分支

退出码：
    0 = 全 OK
    1 = 有异常项
    2 = 命令调用失败
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys


def run_git(args: list[str]) -> tuple[int, str]:
    """运行 git 命令返回 (returncode, stdout)。"""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        return result.returncode, result.stdout.strip()
    except Exception as e:
        return 2, f"ERROR: {e}"


def get_git_mode() -> str:
    return os.environ.get("GIT_MODE", "single").lower()


def check_six_dimensions(branch: str | None = None) -> dict:
    """收集 6 维状态。"""
    if not branch:
        _, branch = run_git(["symbolic-ref", "--short", "HEAD"])
    remote_ref = f"origin/{branch}"

    # 1. 工作树
    _, status = run_git(["status", "--porcelain"])
    working_tree_clean = (status == "")
    working_tree_count = len([l for l in status.split("\n") if l.strip()])

    # 2/3/4. 本地 vs 远程
    rc_local, local_head = run_git(["rev-parse", "HEAD"])
    rc_remote, remote_head = run_git(["rev-parse", remote_ref])
    if rc_local != 0 or rc_remote != 0:
        local_eq_remote = False
        ahead = -1
        behind = -1
    else:
        local_eq_remote = (local_head == remote_head)
        _, ahead_str = run_git(["rev-list", "--count", f"{remote_ref}..HEAD"])
        _, behind_str = run_git(["rev-list", "--count", f"HEAD..{remote_ref}"])
        ahead = int(ahead_str) if ahead_str.isdigit() else -1
        behind = int(behind_str) if behind_str.isdigit() else -1

    # 5. 未跟踪
    _, untracked_str = run_git(["ls-files", "--others", "--exclude-standard"])
    untracked_count = len([l for l in untracked_str.split("\n") if l.strip()])

    # 6. 最新 commit
    _, last_commit = run_git(["log", "-1", "--format=%h %s"])

    return {
        "branch": branch,
        "working_tree_clean": working_tree_clean,
        "working_tree_count": working_tree_count,
        "local_head": local_head[:8] if local_head else "?",
        "remote_head": remote_head[:8] if remote_head else "?",
        "local_eq_remote": local_eq_remote,
        "ahead": ahead,
        "behind": behind,
        "untracked_count": untracked_count,
        "last_commit": last_commit[:80],
        "git_mode": get_git_mode(),
    }


def format_report(result: dict) -> str:
    """markdown 表格输出。"""
    lines = []
    lines.append(f"# git 同步状态核查（branch = {result['branch']}）")
    lines.append("")
    lines.append(f"GIT_MODE: **{result['git_mode']}**")
    lines.append("")
    lines.append("| 维度 | 期望 | 实际 | 状态 |")
    lines.append("|------|------|------|------|")
    lines.append(f"| 1. 工作树 | clean | {result['working_tree_count']} 文件 | {'✅' if result['working_tree_clean'] else '❌'} |")
    lines.append(f"| 2. 本地 HEAD | == 远程 | {result['local_head']} vs {result['remote_head']} | {'✅' if result['local_eq_remote'] else '❌'} |")
    lines.append(f"| 3. ahead | 0 | {result['ahead']} | {'✅' if result['ahead'] == 0 else '❌'} |")
    lines.append(f"| 4. behind | 0 | {result['behind']} | {'✅' if result['behind'] == 0 else '❌'} |")
    lines.append(f"| 5. untracked | 0 | {result['untracked_count']} | {'✅' if result['untracked_count'] == 0 else '⚠️'} |")
    lines.append(f"| 6. 最新 commit | - | `{result['last_commit']}` | - |")
    return "\n".join(lines)


def is_all_ok(result: dict, strict: bool = False) -> bool:
    """判断是否全 OK。strict 模式下 untracked > 0 也视为不 OK。"""
    base = (
        result["working_tree_clean"]
        and result["local_eq_remote"]
        and result["ahead"] == 0
        and result["behind"] == 0
    )
    if strict:
        return base and result["untracked_count"] == 0
    return base


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="6 维 git 同步状态核查")
    parser.add_argument("--for-push", action="store_true", help="严格模式（pre-push hook 用）")
    parser.add_argument("--report", action="store_true", help="markdown 报表（默认）")
    parser.add_argument("--branch", help="指定分支（默认当前分支）")
    parser.add_argument("--quiet", action="store_true", help="仅输出退出码")
    args = parser.parse_args(argv)

    result = check_six_dimensions(args.branch)
    ok = is_all_ok(result, strict=args.for_push)

    if not args.quiet:
        print(format_report(result))
        if not ok:
            print()
            if not result["working_tree_clean"]:
                print("⚠️  工作树有未提交变更，先 `git add + commit` 或 `git stash`")
            if result["behind"] > 0:
                print(f"⚠️  落后远程 {result['behind']} commit，先 `git pull --rebase`")
            if result["ahead"] > 0:
                print(f"💡 领先远程 {result['ahead']} commit，准备 `git push`")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
