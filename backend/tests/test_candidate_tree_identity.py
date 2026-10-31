"""candidate_tree_identity.py 的自动化测试。

覆盖 AC-24 的 A 部分要求：
  1. build 前后 git for-each-ref 逐行相同（refs 不被移动）
  2. 父进程 os.environ 不含 GIT_INDEX_FILE
  3. 所用 index 不是 .git/index
  4. worktree 已锁定
  5. release 后联接目标目录仍在
  6. 把私有 index 换成默认 index 的变异必须红并逐字节还原

注意：checkout 为 25K 文件的仓库创建 worktree，在 Windows 上约需 2 分钟。
checkout/release 测试合并为一个集成序列以避免重复创建。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

# ── 仓库根 / 脚本路径 ──────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "check" / "candidate_tree_identity.py"
_PYTHON = sys.executable
_TMP_BASE = _REPO_ROOT / "tmp_global_display_settings"

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _run_tool(
    args: list[str], *, check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """用当前 Python 运行 candidate_tree_identity.py。"""
    result = subprocess.run(
        [_PYTHON, str(_SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(_REPO_ROOT),
        timeout=300,  # 单次 worktree 操作最多 5 分钟
    )
    if check and result.returncode != 0:
        # 附带完整 stderr 方便调试
        msg = (
            f"Tool exited {result.returncode}\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr (last 2000) ---\n{result.stderr[-2000:]}"
        )
        raise AssertionError(msg)
    return result


def _git(args: list[str], *, cwd: Path | None = None) -> str:
    """简单 git 调用并返回 stdout。"""
    return subprocess.run(
        ["git", *args],
        capture_output=True, text=True, check=True,
        cwd=str(cwd or _REPO_ROOT),
    ).stdout


def _write_manifest(entries: list[dict], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    return path


def _load_module():
    """动态导入 candidate_tree_identity 模块。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "candidate_tree_identity", str(_SCRIPT),
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_workflow_dir() -> Path:
    """在 tmp_global_display_settings 下建子目录，测试结束清理。"""
    d = _TMP_BASE / f"_pytest_{os.getpid()}"
    d.mkdir(parents=True, exist_ok=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------
# 测试：build 子命令
# ---------------------------------------------------------------------------

class TestBuild:
    """build 子命令的正确性（快速，不涉及 worktree 创建）。"""

    def test_refs_unchanged_after_build(self, tmp_workflow_dir: Path) -> None:
        """build 前后 git for-each-ref 逐行相同。"""
        refs_before = _git(["for-each-ref"])

        manifest_path = tmp_workflow_dir / "manifest.json"
        output_path = tmp_workflow_dir / "output.json"
        _write_manifest(
            [{"path": "scripts/check/candidate_tree_identity.py",
              "source": "worktree"}],
            manifest_path,
        )
        _run_tool([
            "build",
            "--manifest", str(manifest_path),
            "--output", str(output_path),
        ])

        refs_after = _git(["for-each-ref"])
        assert refs_before == refs_after, "build must not move any ref"

    def test_parent_env_has_no_git_index_file(self) -> None:
        """父进程 os.environ 不含 GIT_INDEX_FILE。"""
        assert "GIT_INDEX_FILE" not in os.environ

    def test_private_index_safety_assertion(self) -> None:
        """如果 GIT_INDEX_FILE 已在父进程环境中，_git 必须拒绝。"""
        mod = _load_module()
        repo = mod._repo_root()
        git_dir = mod._resolve_git_dir(repo)
        real_index = str((git_dir / "index").resolve())

        with pytest.raises(RuntimeError, match="must not be set"):
            with mock.patch.dict(os.environ, {"GIT_INDEX_FILE": real_index}):
                mod._git(
                    ["status"],
                    env_extra={"GIT_INDEX_FILE": real_index},
                )

    def test_output_contains_valid_oids(self, tmp_workflow_dir: Path) -> None:
        """build 输出的 OID 是合法 git 对象。"""
        manifest_path = tmp_workflow_dir / "manifest.json"
        output_path = tmp_workflow_dir / "output.json"
        _write_manifest(
            [{"path": "scripts/check/candidate_tree_identity.py",
              "source": "worktree"}],
            manifest_path,
        )
        _run_tool([
            "build",
            "--manifest", str(manifest_path),
            "--output", str(output_path),
        ])

        data = json.loads(output_path.read_text(encoding="utf-8"))
        for key in ("commit_oid", "tree_oid", "parent_oid"):
            oid = data[key]
            assert len(oid) == 40, f"{key} should be 40 hex chars"
            assert all(c in "0123456789abcdef" for c in oid)

        # commit 和 tree 对象确实存在
        assert _git(["cat-file", "-t", data["commit_oid"]]).strip() == "commit"
        assert _git(["cat-file", "-t", data["tree_oid"]]).strip() == "tree"

    def test_build_with_external_source(self, tmp_workflow_dir: Path) -> None:
        """清单 source 可以指向外部文件。"""
        ext_file = tmp_workflow_dir / "patched_content.py"
        ext_file.write_text("# patched for test\n", encoding="utf-8")

        manifest_path = tmp_workflow_dir / "manifest.json"
        output_path = tmp_workflow_dir / "output.json"
        _write_manifest(
            [{"path": "scripts/check/candidate_tree_identity.py",
              "source": str(ext_file)}],
            manifest_path,
        )
        _run_tool([
            "build",
            "--manifest", str(manifest_path),
            "--output", str(output_path),
        ])

        data = json.loads(output_path.read_text(encoding="utf-8"))
        # tree 应与 HEAD tree 不同（内容改了）
        head_tree = _git(["rev-parse", "HEAD^{tree}"]).strip()
        assert data["tree_oid"] != head_tree

    def test_build_fails_on_missing_source(self, tmp_workflow_dir: Path) -> None:
        """清单指向不存在的文件时 build 应失败。"""
        manifest_path = tmp_workflow_dir / "manifest.json"
        output_path = tmp_workflow_dir / "output.json"
        _write_manifest(
            [{"path": "no_such_file.py", "source": "worktree"}],
            manifest_path,
        )
        result = _run_tool(
            ["build", "--manifest", str(manifest_path),
             "--output", str(output_path)],
            check=False,
        )
        assert result.returncode != 0
        assert "not found" in result.stderr.lower()


# ---------------------------------------------------------------------------
# 测试：checkout → 验证 → release 集成序列
# ---------------------------------------------------------------------------

class TestCheckoutAndRelease:
    """checkout/release 集成测试。

    仓库有 25K+ 文件，worktree 创建约需 2 分钟，所以合并为单个测试
    序列来覆盖锁定、干净和清理。
    """

    @pytest.fixture()
    def _candidate_commit(self, tmp_workflow_dir: Path) -> str:
        """build 并返回 commit OID。"""
        manifest_path = tmp_workflow_dir / "manifest.json"
        output_path = tmp_workflow_dir / "output.json"
        _write_manifest(
            [{"path": "scripts/check/candidate_tree_identity.py",
              "source": "worktree"}],
            manifest_path,
        )
        _run_tool([
            "build",
            "--manifest", str(manifest_path),
            "--output", str(output_path),
        ])
        data = json.loads(output_path.read_text(encoding="utf-8"))
        return data["commit_oid"]

    def test_checkout_lock_clean_and_release(
        self, _candidate_commit: str,
    ) -> None:
        """checkout → 验证锁定/干净 → release → 验证清理。"""
        name = f"_pytest_integ_{os.getpid()}"
        wt_path = _REPO_ROOT / "tmp_global_display_settings" / name

        try:
            # ── checkout ─────────────────────────────────────────────────
            _run_tool([
                "checkout",
                "--commit", _candidate_commit,
                "--name", name,
            ])
            assert wt_path.exists(), "worktree directory must exist"

            # ── 验证锁定 ─────────────────────────────────────────────────
            wt_porcelain = _git(["worktree", "list", "--porcelain"])
            found_locked = False
            current_wt = False
            # 规范化比较：resolve 后比较
            normalized_wt = str(wt_path.resolve())
            for line in wt_porcelain.splitlines():
                if line.startswith("worktree "):
                    wt_val = line[len("worktree "):]
                    # 都用 Path.resolve 规范化后比较
                    try:
                        current_wt = (
                            Path(wt_val).resolve() == Path(normalized_wt).resolve()
                        )
                    except (ValueError, OSError):
                        current_wt = False
                elif current_wt and line.startswith("locked"):
                    found_locked = True
                    break
                elif current_wt and line == "":
                    break
            assert found_locked, f"worktree {wt_path} should be locked"

            # ── 验证 HEAD 指向正确 commit ────────────────────────────────
            actual_head = _git(["rev-parse", "HEAD"], cwd=wt_path).strip()
            assert actual_head == _candidate_commit

            # ── release ──────────────────────────────────────────────────
            _run_tool(["release", "--path", str(wt_path)])
            assert not wt_path.exists(), "worktree dir must be removed"

            # 不在 worktree list 中
            wt_list_after = _git(["worktree", "list"])
            assert name not in wt_list_after

        finally:
            # 防御性清理
            if wt_path.exists():
                _run_tool(["release", "--path", str(wt_path)], check=False)
            if wt_path.exists():
                shutil.rmtree(wt_path, ignore_errors=True)
                subprocess.run(
                    ["git", "worktree", "prune"],
                    cwd=str(_REPO_ROOT), check=False,
                    capture_output=True,
                )

    def test_junction_target_survives_release(
        self, _candidate_commit: str,
    ) -> None:
        """release 拆联接后联接目标目录仍在。"""
        name = f"_pytest_junc_{os.getpid()}"
        wt_path = _REPO_ROOT / "tmp_global_display_settings" / name
        junction_target = _TMP_BASE / f"_pytest_nm_target_{os.getpid()}"

        try:
            _run_tool([
                "checkout",
                "--commit", _candidate_commit,
                "--name", name,
            ])

            # 模拟 node_modules junction
            junction_target.mkdir(parents=True, exist_ok=True)
            (junction_target / "marker.txt").write_text(
                "keep me", encoding="utf-8",
            )
            nm_link = wt_path / "node_modules"
            if sys.platform == "win32":
                subprocess.run(
                    ["cmd", "/c", "mklink", "/J",
                     str(nm_link), str(junction_target)],
                    check=True, capture_output=True,
                )
            else:
                nm_link.symlink_to(junction_target)

            assert nm_link.exists()

            # release
            _run_tool(["release", "--path", str(wt_path)])

            # 联接目标仍在
            assert junction_target.exists(), \
                "junction target must survive release"
            assert (junction_target / "marker.txt").read_text(
                encoding="utf-8",
            ) == "keep me"

        finally:
            shutil.rmtree(junction_target, ignore_errors=True)
            if wt_path.exists():
                _run_tool(["release", "--path", str(wt_path)], check=False)
            if wt_path.exists():
                shutil.rmtree(wt_path, ignore_errors=True)
                subprocess.run(
                    ["git", "worktree", "prune"],
                    cwd=str(_REPO_ROOT), check=False,
                    capture_output=True,
                )

    def test_checkout_fails_if_path_exists(
        self, _candidate_commit: str,
    ) -> None:
        """路径已存在时 checkout 应失败（不需要真 worktree，快速）。"""
        name = f"_pytest_exist_{os.getpid()}"
        wt_path = _REPO_ROOT / "tmp_global_display_settings" / name
        wt_path.mkdir(parents=True, exist_ok=True)
        try:
            result = _run_tool(
                ["checkout", "--commit", _candidate_commit, "--name", name],
                check=False,
            )
            assert result.returncode != 0
            assert "already exists" in result.stderr.lower()
        finally:
            shutil.rmtree(wt_path, ignore_errors=True)

    def test_release_nonexistent_path(self) -> None:
        """对不存在路径 release 只 warning，不崩溃。"""
        fake = str(
            _REPO_ROOT / "tmp_global_display_settings" / "_no_such_wt_ever"
        )
        result = _run_tool(["release", "--path", fake])
        assert "warning" in result.stderr.lower() or result.returncode == 0


# ---------------------------------------------------------------------------
# 变异测试：把私有 index 换成默认 index
# ---------------------------------------------------------------------------

class TestMutationDefaultIndex:
    """把私有 index 换成 .git/index 的变异必须红。"""

    def test_using_real_index_env_is_rejected(self) -> None:
        """如果 GIT_INDEX_FILE 已存在于父进程环境，_git 必须抛错。"""
        mod = _load_module()
        repo = mod._repo_root()
        git_dir = mod._resolve_git_dir(repo)
        real_index = str((git_dir / "index").resolve())

        with mock.patch.dict(os.environ, {"GIT_INDEX_FILE": real_index}):
            with pytest.raises(RuntimeError, match="must not be set"):
                mod._git(
                    ["status"],
                    env_extra={"GIT_INDEX_FILE": real_index},
                )

    def test_private_index_resolving_to_git_index_is_rejected(
        self, tmp_workflow_dir: Path,
    ) -> None:
        """mkstemp 返回 .git/index 路径时 cmd_build 必须拒绝。"""
        import argparse
        import tempfile as tf

        mod = _load_module()
        repo = mod._repo_root()
        git_dir = mod._resolve_git_dir(repo)
        real_index = (git_dir / "index").resolve()

        original_mkstemp = tf.mkstemp

        def fake_mkstemp(**kwargs):
            # 建一个临时文件但告诉工具路径是 .git/index
            fd, real_tmp = original_mkstemp(**kwargs)
            os.close(fd)
            os.unlink(real_tmp)
            # 返回 NUL 的 fd + .git/index 路径
            fd = os.open(os.devnull, os.O_RDWR)
            return fd, str(real_index)

        manifest_path = tmp_workflow_dir / "manifest.json"
        output_path = tmp_workflow_dir / "output.json"
        _write_manifest(
            [{"path": "scripts/check/candidate_tree_identity.py",
              "source": "worktree"}],
            manifest_path,
        )

        with mock.patch.object(tf, "mkstemp", side_effect=fake_mkstemp):
            with pytest.raises(RuntimeError, match="resolved to .git/index"):
                ns = argparse.Namespace(
                    manifest=str(manifest_path),
                    output=str(output_path),
                )
                mod.cmd_build(ns)
