"""运行时快照清理的两条保证（RV13.1-01，design §8.4）。

开发后端 --reload 出的每个 worker 都跑启动任务 acnr_catalog_snapshot_gc。修复前引用集读进程内
归档字典（冷启动为空），keep_recent=10 之外的已提交快照被删（13 份删 3 份，见续做记录第十四段）。
现在：
1. 引用集只认数据库，证实不了（T17 前没有锁定列 / 查库失败 / 没有会话）→ 一个都不删；
2. 已登记进仓库（git 索引）的快照运行时一律不删；判定不了哪些已登记 → 一个都不删；
3. 未登记的散落快照在引用集已证实时仍按 keep_recent + 未被引用清理。
全部在临时目录上跑，不读写仓库里的快照目录（最后一例只读 git 索引）。
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from app.core import startup_registry
from app.services.acnr import catalog_snapshot_gc as gc_mod

_BACKEND = Path(__file__).resolve().parents[2]
_REAL_SNAPSHOTS = _BACKEND / "data" / "acnr" / "catalog_snapshots"
_VERSIONS = [f"202610{d:02d}000000" for d in range(1, 14)]  # 13 份，最旧 3 份落在 keep_recent=10 之外
_OLDEST_3 = _VERSIONS[:3]

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="本机没有 git")


def _write_snapshots(d: Path, versions: list[str]) -> None:
    for v in versions:
        (d / f"{v}.json").write_text(json.dumps({"registry_version": v}), encoding="utf-8")


def _git(d: Path, *args: str) -> None:
    env = {k: v for k, v in os.environ.items() if k not in gc_mod._GIT_REDIRECT_ENV}
    subprocess.run(["git", "-C", str(d), *args], check=True, capture_output=True, env=env)


def _repo(tmp_path: Path, *, registered: list[str], untracked: list[str]) -> Path:
    """临时 git 仓库：registered 登记进索引，untracked 只落盘。"""
    d = tmp_path / "catalog_snapshots"
    d.mkdir()
    _git(d, "init", "-q")
    _write_snapshots(d, registered)
    if registered:
        _git(d, "add", "--", *[f"{v}.json" for v in registered])
    _write_snapshots(d, untracked)
    return d


def _remaining(d: Path) -> list[str]:
    return sorted(p.stem for p in d.glob("*.json"))


def _db_verified(monkeypatch, refs: set[str]) -> None:
    """数据库已证实引用集。

    两个入口都要替换：带会话走 `referenced_registry_versions`，不带会话（启动任务）走
    `_referenced_versions_with_own_session` 自开短会话 —— 只替换前者，后者会真去连库、
    在测试环境连不上就返回 None，用例会变成「不可验证」而不是本函数想模拟的「已证实」。
    """
    async def _fake(_db):
        return set(refs)

    async def _fake_own():
        return set(refs)

    monkeypatch.setattr(gc_mod, "referenced_registry_versions", _fake)
    monkeypatch.setattr(gc_mod, "_referenced_versions_with_own_session", _fake_own)


def _db_unverifiable(monkeypatch) -> None:
    """数据库证实不了引用集（没有会话 / 开不出会话 / 查库失败）。"""
    async def _none(_db):
        return None

    async def _none_own():
        return None

    monkeypatch.setattr(gc_mod, "referenced_registry_versions", _none)
    monkeypatch.setattr(gc_mod, "_referenced_versions_with_own_session", _none_own)


# ─── 保证 1：引用集证实不了就一个都不删 ───────────────────────────────────


@needs_git
async def test_cold_start_unverifiable_refs_startup_task_deletes_none(tmp_path, monkeypatch):
    d = _repo(tmp_path, registered=[], untracked=_VERSIONS)  # 13 份都未登记：只有 fail-closed 能保住
    monkeypatch.setenv("ACNR_SNAPSHOTS_DIR", str(d))
    _db_unverifiable(monkeypatch)  # 证实不了（开不出会话 / 查库失败），不是「已证实无引用」
    await startup_registry._task_acnr_catalog_snapshot_gc(None)
    assert _remaining(d) == _VERSIONS
    report = await gc_mod.run_db_aware_gc(keep_recent=10)
    assert report["reference_status"] == "unverifiable"
    assert report["deleted"] == []


@needs_git
async def test_no_session_opens_own_session_and_verifies(tmp_path, monkeypatch):
    """不带会话时自开短会话查引用集（T19 接线）—— 否则启动任务恒 fail-closed，等于摆设。

    这一例把自开入口放回真实实现，只替换 `async_session`，证明「无会话 → 自开 → 查库 → 已证实」
    这条链真的接上了（只替换 referenced_registry_versions 的用例看不出这条链是否存在）。
    """
    strays = ["20260901000000", "20260902000000"]
    d = _repo(tmp_path, registered=_VERSIONS, untracked=strays)
    monkeypatch.setenv("ACNR_SNAPSHOTS_DIR", str(d))

    opened: list[str] = []

    class _FakeSession:
        async def __aenter__(self):
            opened.append("open")
            return self

        async def __aexit__(self, *_exc):
            return False

        async def execute(self, _stmt):
            class _R:
                @staticmethod
                def all():
                    return [("20260902000000",)]  # 这份散落快照被项目锁定
            return _R()

    import app.core.database as db_mod
    monkeypatch.setattr(db_mod, "async_session", lambda: _FakeSession())

    report = await gc_mod.run_db_aware_gc(keep_recent=10)
    assert opened == ["open"], "无会话时没有自开短会话"
    assert report["reference_status"] == "verified"
    # 被锁定的散落快照保住，另一份未被锁定且未提交 → 清理
    assert _remaining(d) == sorted(_VERSIONS + ["20260902000000"])


async def test_own_session_failure_is_fail_closed(tmp_path, monkeypatch):
    """自开会话失败（启动期数据库没就绪）→ 返回 None，不删。"""
    import app.core.database as db_mod

    def _boom():
        raise RuntimeError("数据库没就绪")

    monkeypatch.setattr(db_mod, "async_session", _boom)
    assert await gc_mod._referenced_versions_with_own_session() is None


@needs_git
async def test_db_query_error_fail_closed(tmp_path, monkeypatch):
    d = _repo(tmp_path, registered=[], untracked=_VERSIONS)
    monkeypatch.setenv("ACNR_SNAPSHOTS_DIR", str(d))

    async def _boom(_db):
        raise RuntimeError("查库失败")
    monkeypatch.setattr(gc_mod, "referenced_registry_versions", _boom)
    report = await gc_mod.run_db_aware_gc(keep_recent=10)
    assert report["reference_status"] == "unverifiable"
    assert report["deleted"] == [] and _remaining(d) == _VERSIONS


async def test_referenced_versions_without_session_is_none():
    """没有可用会话 → None，不是空集。

    空集的含义是「已证实没有任何项目锁定快照」，调用方据此动手删；证实不了必须返回 None。
    两者混同就是 RV13.1-01 那个缺陷：冷启动拿不到引用就把被锁定的快照删了。
    """
    assert await gc_mod.referenced_registry_versions(None) is None


async def test_referenced_versions_reads_locked_column_including_soft_deleted():
    """真 ORM 查库：引用集 = `projects.acnr_registry_version` 非空值，**含软删项目**。

    软删只是进了回收站，项目恢复后还要按锁定版本解析 —— 它引用的快照现在就不能删。
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    from app.models.base import Base
    from app.models.core import Project, ProjectStatus, User

    engine = create_async_engine("sqlite+aiosqlite:///:memory:",
                                 connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[User.__table__, Project.__table__])
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with maker() as db:
            import uuid as _uuid

            def _p(name: str, version: str | None, *, deleted: bool = False) -> Project:
                return Project(id=_uuid.uuid4(), name=name, client_name="x",
                               status=ProjectStatus.created, acnr_registry_version=version,
                               is_deleted=deleted)

            db.add_all([
                _p("【测试】锁v1", "20260101000000"),
                _p("【测试】锁v2", "20260202000000"),
                _p("【测试】软删也锁着", "20260303000000", deleted=True),
                _p("【测试】未锁定", None),
            ])
            await db.flush()

            refs = await gc_mod.referenced_registry_versions(db)
            assert refs == {"20260101000000", "20260202000000", "20260303000000"}, refs
    finally:
        await engine.dispose()


def test_gc_module_does_not_read_in_process_dict():
    """引用来源不得是进程内归档字典：模块不 import immutability。"""
    tree = ast.parse(Path(gc_mod.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert not {n for n in imported if "immutability" in n or n == "list_archived_projects"}, imported


# ─── 保证 2：已登记进仓库的快照运行时不删 ─────────────────────────────────


@needs_git
async def test_cold_start_13_registered_startup_task_deletes_none(tmp_path, monkeypatch):
    d = _repo(tmp_path, registered=_VERSIONS, untracked=[])
    monkeypatch.setenv("ACNR_SNAPSHOTS_DIR", str(d))
    _db_verified(monkeypatch, set())  # 即便数据库证实无任何引用
    await startup_registry._task_acnr_catalog_snapshot_gc(None)
    assert _remaining(d) == _VERSIONS
    report = await gc_mod.run_db_aware_gc(keep_recent=10)
    assert report["reference_status"] == "verified" and report["committed_status"] == "verified"
    assert report["deleted"] == [] and sorted(report["skipped_protected"]) == _OLDEST_3


async def test_committed_unknown_when_git_missing(tmp_path, monkeypatch):
    d = tmp_path / "s"
    d.mkdir()
    _write_snapshots(d, _VERSIONS)
    monkeypatch.setenv("ACNR_SNAPSHOTS_DIR", str(d))
    _db_verified(monkeypatch, set())

    def _no_git(*_a, **_k):
        raise FileNotFoundError("git")
    monkeypatch.setattr(gc_mod.subprocess, "run", _no_git)
    assert gc_mod.committed_snapshot_versions(d) is None
    report = await gc_mod.run_db_aware_gc(keep_recent=10)
    assert report["committed_status"] == "unverifiable"
    assert report["deleted"] == [] and _remaining(d) == _VERSIONS


async def test_committed_unknown_when_git_errors(tmp_path, monkeypatch):
    d = tmp_path / "s"
    d.mkdir()
    _write_snapshots(d, _VERSIONS)
    monkeypatch.setenv("ACNR_SNAPSHOTS_DIR", str(d))
    _db_verified(monkeypatch, set())
    monkeypatch.setattr(gc_mod.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 128, b"", b"not a git repository"))
    assert gc_mod.committed_snapshot_versions(d) is None
    report = await gc_mod.run_db_aware_gc(keep_recent=10)
    assert report["deleted"] == [] and _remaining(d) == _VERSIONS


@needs_git
def test_real_registries_are_committed():
    """仓库快照目录：不可变登记里的快照与当前发布批次快照都在 git 索引里（运行时清理据此不删）。"""
    from tests.acnr.test_catalog_index_fail_closed import _SNAPSHOT_CONTENT_SHA256

    committed = gc_mod.committed_snapshot_versions(_REAL_SNAPSHOTS)
    if committed is None:
        pytest.skip("不在 git 检出里")
    release = json.loads((_REAL_SNAPSHOTS.parent / "catalog_report.json").read_text(encoding="utf-8"))
    pinned = {n[: -len(".json")] for n in _SNAPSHOT_CONTENT_SHA256}
    assert pinned | {release["release"]["registry_version"]} <= committed


# ─── 保证 3：未登记的散落快照仍按规则清理 ─────────────────────────────────


@needs_git
async def test_untracked_strays_cleaned_when_refs_verified(tmp_path, monkeypatch):
    strays = ["20260901000000", "20260902000000", "20260903000000"]
    d = _repo(tmp_path, registered=_VERSIONS, untracked=strays)
    monkeypatch.setenv("ACNR_SNAPSHOTS_DIR", str(d))
    _db_verified(monkeypatch, {"20260902000000"})  # 被项目锁定的散落快照不删
    await startup_registry._task_acnr_catalog_snapshot_gc(None)
    assert _remaining(d) == sorted(_VERSIONS + ["20260902000000"])
