"""ACNR 项目版本锁与快照 GC 的共同生命周期锁。

故障注入都放在被测生产函数的下一层：锁 SQL 返回值、项目锁调用的共同锁、GC 调用的共同锁、
Path.unlink。任何一条安全前置被删都应红在对应行为断言，不验证测试里的拷贝。
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from app.services.acnr import catalog_snapshot_gc as gc
from app.services.acnr import project_registry_lock as project_lock
from app.services.acnr import snapshot_lifecycle_lock as lifecycle


class _Dialect:
    def __init__(self, name: str) -> None:
        self.name = name


class _Bind:
    def __init__(self, name: str) -> None:
        self.dialect = _Dialect(name)


class _ScalarResult:
    def __init__(self, value: bool) -> None:
        self.value = value

    def scalar_one(self) -> bool:
        return self.value


class _Db:
    def __init__(self, dialect: str, lock_value: bool = True) -> None:
        self.bind = _Bind(dialect)
        self.lock_value = lock_value
        self.calls: list[tuple[object, object]] = []

    def get_bind(self):
        return self.bind

    async def execute(self, statement, params=None):
        self.calls.append((statement, params))
        return _ScalarResult(self.lock_value)


@pytest.mark.parametrize(
    ("dialect", "lock_value", "expected", "execute_count"),
    [
        ("sqlite", True, "not_required", 0),
        ("mysql", True, "unverifiable", 0),
        ("postgresql", True, "acquired", 1),
        ("postgresql", False, "busy", 1),
    ],
)
async def test_lifecycle_lock_statuses(dialect, lock_value, expected, execute_count):
    db = _Db(dialect, lock_value)
    assert await lifecycle.try_acquire_snapshot_lifecycle_lock(db) == expected
    assert len(db.calls) == execute_count
    if db.calls:
        sql = str(db.calls[0][0])
        assert "pg_try_advisory_xact_lock" in sql
        assert db.calls[0][1] == {
            "namespace": lifecycle.LOCK_NAMESPACE,
            "resource": lifecycle.LOCK_RESOURCE,
        }


async def test_unknown_dialect_is_unverifiable_and_executes_nothing():
    class UnknownDb:
        pass

    assert await lifecycle.try_acquire_snapshot_lifecycle_lock(UnknownDb()) == "unverifiable"


async def test_project_lock_busy_fails_before_snapshot_or_project_access(monkeypatch):
    """GC 持锁时归档须 409 重试，不能先验文件 / 写项目后才发现竞态。"""
    acquire = AsyncMock(return_value="busy")
    verify = Mock(side_effect=AssertionError("锁忙时不应读快照"))
    monkeypatch.setattr(project_lock, "try_acquire_snapshot_lifecycle_lock", acquire)
    monkeypatch.setattr(project_lock, "verify_snapshot", verify)

    with pytest.raises(project_lock.RegistryLockError) as caught:
        await project_lock.lock_project_registry(object(), "p", version="20260101000000")

    assert caught.value.code == "lock_failed"
    assert "正在维护" in caught.value.message
    acquire.assert_awaited_once()
    verify.assert_not_called()


def _write_versions(directory: Path, versions: list[str]) -> None:
    for version in versions:
        (directory / f"{version}.json").write_text(
            json.dumps({"registry_version": version}), encoding="utf-8"
        )


async def test_gc_lock_busy_is_fail_closed_before_query_or_unlink(tmp_path, monkeypatch):
    """归档事务持锁时 GC 直接零删除；删掉共同锁调用后，本例会进入查询桩并红。"""
    versions = [f"202601{day:02d}000000" for day in range(1, 14)]
    _write_versions(tmp_path, versions)
    monkeypatch.setenv("ACNR_SNAPSHOTS_DIR", str(tmp_path))

    async def busy(_db):
        return "busy"

    async def must_not_query(_db):
        raise AssertionError("生命周期锁忙时不应读取一个即将过时的引用集合")

    monkeypatch.setattr(lifecycle, "try_acquire_snapshot_lifecycle_lock", busy)
    monkeypatch.setattr(gc, "referenced_registry_versions", must_not_query)
    report = await gc.run_db_aware_gc(object(), keep_recent=0)

    assert report["lifecycle_lock_status"] == "busy"
    assert report["reference_status"] == "unverifiable"
    assert report["deleted"] == []
    assert sorted(p.stem for p in tmp_path.glob("*.json")) == versions


def test_gc_ignores_non_snapshot_json_and_directories(tmp_path):
    _write_versions(tmp_path, ["20260101000000", "20260102000000"])
    (tmp_path / "notes.json").write_text("{}", encoding="utf-8")
    (tmp_path / "2026010100000.json").write_text("{}", encoding="utf-8")  # 13 位
    (tmp_path / "202601010000000.json").write_text("{}", encoding="utf-8")  # 15 位
    (tmp_path / "20260103000000.json").mkdir()  # 名字像快照，但不是文件

    assert gc.list_snapshot_versions(tmp_path) == ["20260102000000", "20260101000000"]
    report = gc.cleanup_stale_snapshots(
        keep_recent=0,
        snapshots_dir=tmp_path,
        referenced_versions=set(),
    )
    assert report["deleted"] == ["20260102000000", "20260101000000"]
    assert (tmp_path / "notes.json").is_file()
    assert (tmp_path / "2026010100000.json").is_file()
    assert (tmp_path / "202601010000000.json").is_file()
    assert (tmp_path / "20260103000000.json").is_dir()


def test_unlink_failure_is_reported_without_hiding_other_successes(tmp_path, monkeypatch):
    versions = ["20260101000000", "20260102000000"]
    _write_versions(tmp_path, versions)
    original = Path.unlink

    def fail_one(path: Path, *args, **kwargs):
        if path.stem == versions[1]:
            raise PermissionError("测试：文件被占用")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_one)
    report = gc.cleanup_stale_snapshots(
        keep_recent=0,
        snapshots_dir=tmp_path,
        referenced_versions=set(),
    )

    assert report["deleted"] == [versions[0]]
    assert report["failed"] == [{"version": versions[1], "error": "PermissionError: 测试：文件被占用"}]
    assert not (tmp_path / f"{versions[0]}.json").exists()
    assert (tmp_path / f"{versions[1]}.json").exists()


def test_acnr_gc_startup_task_is_registered_exactly_once_after_migrations():
    """启动编排不能漏接、重复接，也不能在迁移前查尚不存在的版本锁列。"""
    from app.core.startup_registry import STARTUP_TASKS

    matches = [task for task in STARTUP_TASKS if task.name == "acnr_catalog_snapshot_gc"]
    assert len(matches) == 1
    task = matches[0]
    assert task.phase == "acnr"
    assert task.criticality == "best_effort"
    assert task.singleton is True
    names = [item.name for item in STARTUP_TASKS]
    assert names.index("acnr_catalog_snapshot_gc") > names.index("migration_mark_complete")


async def test_startup_task_surfaces_unlink_failures_in_best_effort_report(monkeypatch):
    """删除失败不能被启动健康记成 ok；抛出后通用 executor 会记 failed 但不阻断服务。"""
    from app.core import startup_registry

    report = {
        "total_snapshots": 12,
        "deleted": ["20260101000000"],
        "reference_status": "verified",
        "failed": [{"version": "20251231235959", "error": "PermissionError: busy"}],
    }
    monkeypatch.setattr(gc, "run_db_aware_gc", AsyncMock(return_value=report))

    with pytest.raises(RuntimeError, match=r"删除失败 1 项：20251231235959"):
        await startup_registry._task_acnr_catalog_snapshot_gc(None)
