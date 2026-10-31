"""candidate_tree_identity.py — 候选提交与锁定 worktree 工具。

用途：在私有 git index 上生成候选 commit（不移动 ref），建立分离头
worktree 供验证，用完释放。

子命令：
  build      按 JSON 清单在私有 index 生成候选 commit
  checkout   以候选 commit 建分离头 worktree 并锁定
  release    拆 node_modules 联接 → 解锁 → 删目录 → prune

设计依据：design §17 G7、§18 H2。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
_WORKTREE_BASE = "tmp_global_display_settings"
_LOCK_REASON = "candidate verification worktree"

# ---------------------------------------------------------------------------
# 内部 helpers
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    """返回 git 仓库根目录（绝对路径）。"""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
    )
    return Path(result.stdout.strip())


def _git(
    args: list[str],
    *,
    cwd: str | Path | None = None,
    env_extra: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """执行 git 命令。

    *env_extra* 只注入到子进程环境，父进程 ``os.environ`` 不变。
    """
    env: dict[str, str] | None = None
    if env_extra:
        # 安全：父进程环境里绝不能有 GIT_INDEX_FILE
        if "GIT_INDEX_FILE" in os.environ:
            raise RuntimeError(
                "GIT_INDEX_FILE must not be set in the parent process"
            )
        env = {**os.environ, **env_extra}
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=check,
        cwd=cwd,
        env=env,
    )


def _resolve_git_dir(repo: Path) -> Path:
    """获取真实 .git 目录的绝对路径。"""
    raw = _git(["rev-parse", "--git-dir"], cwd=repo).stdout.strip()
    return (repo / raw).resolve()


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

def cmd_build(args: argparse.Namespace) -> None:
    """按清单文件在私有 index 上生成候选 commit（不移动任何 ref）。

    清单 JSON 格式::

        [
          {"path": "backend/app/models/core.py", "source": "worktree"},
          {"path": "INDEX.md", "source": "/abs/path/to/merged_block"}
        ]

    ``source`` 为 ``"worktree"`` 时取工作树当前文件；否则为绝对路径。
    """
    repo = _repo_root()
    manifest_path = Path(args.manifest)
    output_path = Path(args.output)

    # 读取清单
    with open(manifest_path, "r", encoding="utf-8") as f:
        entries: list[dict[str, str]] = json.load(f)

    if not isinstance(entries, list) or not entries:
        print("FATAL: manifest must be a non-empty JSON array", file=sys.stderr)
        sys.exit(1)

    # ── 1. 快照 build 前的全部 refs ──────────────────────────────────────
    refs_before = _git(["for-each-ref"], cwd=repo).stdout

    # ── 2. 创建私有 index ────────────────────────────────────────────────
    fd, private_index = tempfile.mkstemp(
        prefix="gds_candidate_idx_", suffix=".idx",
    )
    os.close(fd)

    try:
        # 安全：私有 index 不能是 .git/index
        git_dir = _resolve_git_dir(repo)
        real_index = (git_dir / "index").resolve()
        if Path(private_index).resolve() == real_index:
            raise RuntimeError(
                "Private index path resolved to .git/index — aborting"
            )

        idx_env = {"GIT_INDEX_FILE": private_index}

        # ── 3. 从 HEAD 填充 ─────────────────────────────────────────────
        _git(["read-tree", "HEAD"], cwd=repo, env_extra=idx_env)

        # ── 4. 逐项更新 ─────────────────────────────────────────────────
        for entry in entries:
            target_path = entry["path"]
            source = entry["source"]

            if source == "worktree":
                source_file = repo / target_path
            else:
                source_file = Path(source)

            if not source_file.is_file():
                print(
                    f"FATAL: source file not found: {source_file}",
                    file=sys.stderr,
                )
                sys.exit(1)

            # 写入 blob 对象
            blob_hash = _git(
                ["hash-object", "-w", "--", str(source_file)],
                cwd=repo,
            ).stdout.strip()

            # 文件 mode
            mode = "100755" if os.access(source_file, os.X_OK) else "100644"

            # 更新私有 index
            _git(
                [
                    "update-index", "--add", "--replace",
                    "--cacheinfo", f"{mode},{blob_hash},{target_path}",
                ],
                cwd=repo,
                env_extra=idx_env,
            )

        # ── 5. write-tree ────────────────────────────────────────────────
        tree_oid = _git(
            ["write-tree"], cwd=repo, env_extra=idx_env,
        ).stdout.strip()

        # ── 6. commit-tree（不移动任何 ref） ─────────────────────────────
        head_oid = _git(["rev-parse", "HEAD"], cwd=repo).stdout.strip()
        commit_oid = _git(
            [
                "commit-tree", tree_oid,
                "-p", head_oid,
                "-m", "candidate commit for verification",
            ],
            cwd=repo,
        ).stdout.strip()

    finally:
        # 清理临时 index
        try:
            os.unlink(private_index)
        except OSError:
            pass

    # ── 7. 验证 refs 未被移动 ────────────────────────────────────────────
    refs_after = _git(["for-each-ref"], cwd=repo).stdout
    if refs_before != refs_after:
        print("FATAL: refs changed during build!", file=sys.stderr)
        sys.exit(1)

    # ── 8. 写输出 ────────────────────────────────────────────────────────
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "commit_oid": commit_oid,
        "tree_oid": tree_oid,
        "parent_oid": head_oid,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"candidate commit: {commit_oid}")
    print(f"candidate tree:   {tree_oid}")
    print(f"output written:   {output_path}")


# ---------------------------------------------------------------------------
# checkout
# ---------------------------------------------------------------------------

def cmd_checkout(args: argparse.Namespace) -> None:
    """以候选 commit 建立分离头 worktree 并锁定。"""
    repo = _repo_root()
    commit_oid = args.commit
    name = args.name

    wt_path = repo / _WORKTREE_BASE / name
    if wt_path.exists():
        print(
            f"FATAL: worktree path already exists: {wt_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    wt_path.parent.mkdir(parents=True, exist_ok=True)

    # 建立分离头 worktree
    # 用 --no-checkout 先建 worktree 结构，再单独 checkout。
    # 仓库有超长路径归档文件，直接 worktree add 会在最后步 "reset
    # index to HEAD" 时 fatal，并删除已创建的目录。分两步可绕开。
    _git(
        ["worktree", "add", "--detach", "--no-checkout",
         str(wt_path), commit_oid],
        cwd=repo,
    )

    # checkout 文件（忽略长路径无法检出的文件）
    checkout_result = _git(
        ["checkout", "-f", "HEAD"],
        cwd=wt_path,
        check=False,
    )

    if not wt_path.exists():
        print(
            f"FATAL: worktree creation failed:\n"
            f"{checkout_result.stderr[-500:]}",
            file=sys.stderr,
        )
        sys.exit(1)

    # 验证 HEAD 指向正确 commit
    head_result = _git(
        ["rev-parse", "HEAD"], cwd=wt_path, check=False,
    )
    actual_head = head_result.stdout.strip()
    if head_result.returncode != 0 or actual_head != commit_oid:
        print(
            f"FATAL: worktree HEAD mismatch or unresolvable: "
            f"expected {commit_oid}, got '{actual_head}'\n"
            f"{head_result.stderr[-300:]}",
            file=sys.stderr,
        )
        sys.exit(1)

    # 锁定
    _git(
        ["worktree", "lock", "--reason", _LOCK_REASON, str(wt_path)],
        cwd=repo,
    )

    # 验证干净（允许因长路径未检出的文件出现在 status 中）
    status_result = _git(
        ["status", "--porcelain"], cwd=wt_path, check=False,
    )
    status = status_result.stdout.strip()
    # 长路径文件会出现在 status 中，因为 index 里有但文件未检出
    # "D " = index 已暂存删除，" D" = 工作区删除
    unexpected = []
    for line in status.splitlines():
        if not line:
            continue
        xy = line[:2]
        # 允许 " D"（工作区删除）和 "D "（index 删除）
        if xy not in (" D", "D "):
            unexpected.append(line)
    if unexpected:
        print(
            f"FATAL: worktree has unexpected changes:\n"
            + "\n".join(unexpected),
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"worktree created and locked: {wt_path}")


# ---------------------------------------------------------------------------
# release
# ---------------------------------------------------------------------------

def _remove_junctions(wt_path: Path) -> None:
    """拆掉 worktree 内的 node_modules 联接（Windows junction）。

    用 ``cmd /c rmdir`` 只拆链接，不删目标目录。
    """
    candidates = [
        wt_path / "audit-platform" / "frontend" / "node_modules",
        wt_path / "frontend" / "node_modules",
        wt_path / "node_modules",
    ]
    for nm in candidates:
        if nm.exists() and nm.is_junction():
            subprocess.run(
                ["cmd", "/c", "rmdir", str(nm)],
                check=False,
                capture_output=True,
            )


def cmd_release(args: argparse.Namespace) -> None:
    """释放 worktree：拆联接 → 解锁 → 删目录 → prune。"""
    repo = _repo_root()
    wt_path = Path(args.path).resolve()

    if not wt_path.exists():
        print(
            f"WARNING: worktree path does not exist: {wt_path}",
            file=sys.stderr,
        )
        _git(["worktree", "prune"], cwd=repo, check=False)
        return

    # 1. 拆 node_modules junction
    _remove_junctions(wt_path)

    # 2. 解锁
    _git(["worktree", "unlock", str(wt_path)], cwd=repo, check=False)

    # 3. 删目录
    if wt_path.exists():
        shutil.rmtree(wt_path, ignore_errors=True)

    # 4. prune
    _git(["worktree", "prune"], cwd=repo)

    print(f"worktree released: {wt_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="候选提交与锁定 worktree 工具",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # -- build --
    p_build = sub.add_parser("build", help="按清单生成候选 commit")
    p_build.add_argument(
        "--manifest", required=True,
        help="JSON 清单文件路径",
    )
    p_build.add_argument(
        "--output", required=True,
        help="输出 JSON 路径（commit/tree OID）",
    )

    # -- checkout --
    p_checkout = sub.add_parser("checkout", help="建分离头 worktree 并锁定")
    p_checkout.add_argument(
        "--commit", required=True,
        help="候选 commit OID",
    )
    p_checkout.add_argument(
        "--name", required=True,
        help="worktree 名称（放在 tmp_global_display_settings/ 下）",
    )

    # -- release --
    p_release = sub.add_parser("release", help="释放 worktree")
    p_release.add_argument(
        "--path", required=True,
        help="worktree 绝对路径",
    )

    parsed = parser.parse_args(argv)

    dispatch = {
        "build": cmd_build,
        "checkout": cmd_checkout,
        "release": cmd_release,
    }
    dispatch[parsed.command](parsed)


if __name__ == "__main__":
    main()
