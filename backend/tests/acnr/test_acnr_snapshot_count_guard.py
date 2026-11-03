"""RV14.1-01：CI 快照门禁与运行时清理同一判据（按版本集合核对，不按数量抵消）。"""
from __future__ import annotations

import ast
import json
import os
import subprocess
from pathlib import Path

from app.services.acnr import catalog_snapshot_gc as gc_mod
from scripts.check import check_acnr_snapshot_count as guard

_BACKEND = Path(__file__).resolve().parents[2]
_COMMITTED = [f"202610{day:02d}000000" for day in range(1, 14)]  # 13 份，多于 keep_recent=10


def _git(directory: Path, *args: str) -> None:
    env = {k: v for k, v in os.environ.items() if k not in guard.gc._GIT_REDIRECT_ENV}
    subprocess.run(["git", "-C", str(directory), *args], check=True, capture_output=True, env=env)


def _repo(tmp_path: Path, *, committed: list[str], untracked: list[str]) -> Path:
    directory = tmp_path / "catalog_snapshots"
    directory.mkdir()
    _git(directory, "init", "-q")
    for version in committed + untracked:
        (directory / f"{version}.json").write_text(json.dumps({"registry_version": version}), encoding="utf-8")
    if committed:
        _git(directory, "add", "--", *[f"{v}.json" for v in committed])
    return directory


def test_real_committed_snapshots_pass_strict():
    """本仓库快照目录：已登记的快照多于 keep_recent 也不算违规（旧口径在此 exit 1）。"""
    assert guard.main(["--strict"]) == 0


def test_committed_beyond_keep_recent_pass_strict(tmp_path):
    """13 份全部已登记、没有散落 → 通过；旧口径按总数比 keep_recent + 被引用数会报超限。"""
    directory = _repo(tmp_path, committed=_COMMITTED, untracked=[])
    versions, committed, strays = guard.lifecycle_problems(directory, keep_recent=10, referenced_versions=set())
    assert len(versions) == 13 > 10 and committed == frozenset(_COMMITTED) and strays == []
    assert guard.main(["--strict", "--snapshots-dir", str(directory)]) == 0


def test_old_uncommitted_unreferenced_snapshot_fails(tmp_path):
    directory = _repo(tmp_path, committed=_COMMITTED[:12], untracked=["20250101000000"])
    assert guard.main(["--strict", "--snapshots-dir", str(directory)]) == 1
    assert guard.main(["--snapshots-dir", str(directory)]) == 0  # 非 strict 只报告


def test_recent_uncommitted_snapshot_is_not_a_stray(tmp_path):
    """刚发布、还没提交的新快照在最近 keep_recent 份之内 → 不算违规。"""
    directory = _repo(tmp_path, committed=_COMMITTED[:12], untracked=["20261101000000"])
    _, _, strays = guard.lifecycle_problems(directory, keep_recent=10, referenced_versions=set())
    assert strays == []


def test_exact_reference_protects_only_its_version(tmp_path):
    directory = _repo(tmp_path, committed=_COMMITTED[:12], untracked=["20250101000000", "20250202000000"])
    assert guard.main([
        "--strict", "--snapshots-dir", str(directory), "--referenced-version", "20250101000000",
    ]) == 1
    _, _, strays = guard.lifecycle_problems(
        directory, keep_recent=10, referenced_versions={"20250101000000"}
    )
    assert strays == ["20250202000000"]


def test_git_registration_unknown_is_fail_closed(tmp_path, monkeypatch):
    directory = tmp_path / "catalog_snapshots"
    directory.mkdir()
    (directory / "20250101000000.json").write_text("{}", encoding="utf-8")

    def _git_missing(*_a, **_k):
        raise OSError("git missing")

    monkeypatch.setattr(guard.gc.subprocess, "run", _git_missing)
    assert guard.main(["--strict", "--snapshots-dir", str(directory)]) == 2
    assert guard.main(["--snapshots-dir", str(directory)]) == 0


async def test_strays_equal_what_runtime_gc_would_delete(tmp_path, monkeypatch):
    """门禁报的散落快照，恰是引用集已证实时运行时清理入口（run_db_aware_gc）会删的那些。"""
    locked, stray = "20250101000000", "20250202000000"
    directory = _repo(tmp_path, committed=_COMMITTED[:12], untracked=[locked, stray])
    _, _, strays = guard.lifecycle_problems(directory, keep_recent=10, referenced_versions={locked})

    async def _verified():
        return {locked}

    monkeypatch.setenv("ACNR_SNAPSHOTS_DIR", str(directory))
    monkeypatch.setattr(gc_mod, "_referenced_versions_with_own_session", _verified)
    report = await gc_mod.run_db_aware_gc(keep_recent=10, dry_run=True)
    assert report["reference_status"] == "verified"
    assert sorted(report["deleted"]) == strays == [stray]


def test_guard_reuses_runtime_gc_rule():
    """门禁不另写一份判据：按文件加载运行时清理模块，经它判「已登记」与「会被删」，自身不调 git（AST）。"""
    assert Path(guard.gc.__file__).resolve() == (_BACKEND / "app/services/acnr/catalog_snapshot_gc.py").resolve()
    tree = ast.parse(Path(guard.__file__).read_text(encoding="utf-8"))
    imported = {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
    assert "subprocess" not in imported
    strings = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert "ls-files" not in strings
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "lifecycle_problems")
    used = {n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
            and n.value.id == "gc"}
    assert {"list_snapshot_versions", "committed_snapshot_versions", "cleanup_stale_snapshots"} <= used, used
