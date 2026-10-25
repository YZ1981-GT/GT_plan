"""守卫自测：tests/_tracked_write_guard.py（formula-fetch-followup-defect-closure 6.6）。

端到端用例在临时 git 仓库里起子进程 pytest（只加载守卫插件），按真实退出码与输出判定：
改了已跟踪文件不还原 ⇒ 退出码 1 并点名文件与首次写入的用例；写完还原、写未跟踪文件 ⇒ 放行。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from tests import _tracked_write_guard as guard

BACKEND = Path(__file__).resolve().parents[1]
_GIT = shutil.which("git")


class TestWriteDetection:
    @pytest.mark.parametrize(
        ("mode", "flags", "expected"),
        [
            ("r", 0, False),
            ("rb", 0, False),
            ("w", 0, True),
            ("wb", 0, True),
            ("a", 0, True),
            ("x", 0, True),
            ("r+", 0, True),
            (None, os.O_RDONLY, False),
            (None, os.O_WRONLY, True),
            (None, os.O_RDWR, True),
            (None, os.O_RDONLY | os.O_CREAT, True),
        ],
    )
    def test_is_write_open(self, mode, flags, expected):
        assert guard.is_write_open(mode, flags) is expected

    def test_write_targets_by_event(self):
        assert guard.write_targets("open", ("a.txt", "w", 0)) == ("a.txt",)
        assert guard.write_targets("open", ("a.txt", "r", 0)) == ()
        assert guard.write_targets("os.rename", ("src", "dst", -1, -1)) == ("src", "dst")
        assert guard.write_targets("os.remove", ("a.txt", -1)) == ("a.txt",)
        assert guard.write_targets("os.truncate", ("a.txt", 0)) == ("a.txt",)
        assert guard.write_targets("_winapi.CopyFile2", ("src", "dst", 8)) == ("dst",)
        assert guard.write_targets("os.listdir", (".",)) == ()

    def test_normalize_skips_file_descriptors(self):
        assert guard.normalize(3) is None
        assert guard.normalize(Path("x")) == os.path.normcase(os.path.abspath("x"))


def test_guard_is_registered_and_armed_in_this_session(request):
    """真实套件的 root conftest 登记了守卫，且本会话已武装（不在 git 工作树里时才允许不武装）。"""
    assert request.config.pluginmanager.has_plugin(guard.PLUGIN_NAME), (
        "backend/tests/conftest.py 没有登记 _tracked_write_guard"
    )
    if os.environ.get(guard.ALLOW_ENV) == "1":
        pytest.skip(f"{guard.ALLOW_ENV}=1：显式放行重写快照")
    if guard.tracked_files(BACKEND) is None:
        pytest.skip("不在 git 工作树里")
    assert guard.STATE.armed is True
    assert len(guard.STATE.tracked) > 1000
    conftest = guard.normalize(Path(__file__).with_name("conftest.py"))
    assert guard.STATE.tracked.get(conftest) == "backend/tests/conftest.py"


_CONFTEST_WRITES_AT_SESSIONFINISH = '''
from pathlib import Path


def pytest_sessionfinish(session, exitstatus):
    Path(__file__).with_name("session_report.txt").write_text("changed", encoding="utf-8")
'''

_TESTS = {
    "test_bad.py": '''
        import os
        import shutil
        from pathlib import Path

        HERE = Path(__file__).parent

        def test_bad():
            (HERE / "data.txt").write_text("changed", encoding="utf-8")

        def test_atomic_replace():  # 先写临时文件再 os.replace：已跟踪文件上只有一次改名事件
            (HERE / "atomic.tmp").write_text("changed", encoding="utf-8")
            os.replace(HERE / "atomic.tmp", HERE / "atomic.txt")

        def test_copy2():  # Windows 上 shutil.copy2 不经 open，走 _winapi.CopyFile2
            (HERE / "copy_src.tmp").write_text("changed", encoding="utf-8")
            shutil.copy2(HERE / "copy_src.tmp", HERE / "copied.txt")

        def test_remove():
            (HERE / "removed.txt").unlink()
    ''',
    "test_restore.py": '''
        import os
        from pathlib import Path

        def test_restore():
            target = Path(__file__).with_name("restored.txt")
            original = target.read_bytes()
            try:
                target.write_text("mutated", encoding="utf-8")
                os.replace(target, target.with_name("restored.moved"))
                os.replace(target.with_name("restored.moved"), target)
            finally:
                target.write_bytes(original)
    ''',
    "test_untracked.py": '''
        from pathlib import Path

        def test_untracked():
            Path(__file__).with_name("new.txt").write_text("fresh", encoding="utf-8")
    ''',
}


_BAD_TRACKED = ("data.txt", "atomic.txt", "copied.txt", "removed.txt")


def _make_repo(tmp_path: Path, *, tests: dict[str, str], tracked: tuple[str, ...]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    for name in (*_BAD_TRACKED, "restored.txt", "session_report.txt"):
        (repo / name).write_text("original", encoding="utf-8")
    for name, body in tests.items():
        (repo / name).write_text(textwrap.dedent(body), encoding="utf-8")
    subprocess.run([_GIT, "init", "-q"], cwd=repo, check=True)
    subprocess.run([_GIT, "add", "--", *tracked], cwd=repo, check=True)
    return repo


def _run(repo: Path, **extra_env: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != guard.ALLOW_ENV}
    env.update(PYTHONPATH=str(BACKEND), PYTHONIOENCODING="utf-8", **extra_env)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider",
         "-p", "no:playwright", "-p", "tests._tracked_write_guard"],
        cwd=repo, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=180,
    )


@pytest.mark.skipif(_GIT is None, reason="git 不可用")
class TestGuardEndToEnd:
    def test_unrestored_write_fails_run_and_names_file_and_writer(self, tmp_path):
        repo = _make_repo(tmp_path, tests=_TESTS, tracked=(*_BAD_TRACKED, "restored.txt"))
        proc = _run(repo)
        out = proc.stdout + proc.stderr
        assert "6 passed" in out, out
        assert proc.returncode == 1, out
        assert "用例改写了已跟踪文件" in out, out
        for name, writer in (("data.txt", "test_bad"), ("atomic.txt", "test_atomic_replace"),
                             ("copied.txt", "test_copy2"), ("removed.txt", "test_remove")):
            assert f"{name}  ← 首次写入：test_bad.py::{writer}" in out, out
        assert "restored.txt" not in out, out  # 写完还原（含 os.replace 往返）放行
        assert "new.txt" not in out, out  # 未跟踪文件不管
        assert ".tmp" not in out, out

    def test_restored_and_untracked_writes_pass(self, tmp_path):
        tests = {k: v for k, v in _TESTS.items() if k != "test_bad.py"}
        repo = _make_repo(tmp_path, tests=tests, tracked=(*_BAD_TRACKED, "restored.txt"))
        proc = _run(repo)
        out = proc.stdout + proc.stderr
        assert "2 passed" in out, out
        assert proc.returncode == 0, out
        assert "用例改写了已跟踪文件" not in out, out

    def test_conftest_sessionfinish_write_is_caught(self, tmp_path):
        tests = {"test_untracked.py": _TESTS["test_untracked.py"]}
        repo = _make_repo(tmp_path, tests=tests, tracked=("session_report.txt",))
        (repo / "conftest.py").write_text(_CONFTEST_WRITES_AT_SESSIONFINISH, encoding="utf-8")
        proc = _run(repo)
        out = proc.stdout + proc.stderr
        assert proc.returncode == 1, out
        assert "session_report.txt  ← 首次写入：<会话收尾（pytest_sessionfinish）>" in out, out

    def test_opt_in_env_disables_guard(self, tmp_path):
        repo = _make_repo(tmp_path, tests=_TESTS, tracked=(*_BAD_TRACKED, "restored.txt"))
        proc = _run(repo, **{guard.ALLOW_ENV: "1"})
        out = proc.stdout + proc.stderr
        assert "6 passed" in out, out
        assert proc.returncode == 0, out
        assert "用例改写了已跟踪文件" not in out, out
