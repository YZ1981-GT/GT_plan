"""一次性库判定（spec formula-hub-integrity-closure，ADR-FHIC-25；CI 两个 PG job 的库名决定）。

提交型夹具（``committed_project``）与含 DDL 的重放只在可丢弃的库上执行：快照库（``fh_snap_`` 开头），或由
``GT_PG_DISPOSABLE_DB`` 精确点名的一次性库（CI service 容器新建、只跑过迁移）。共享库 ``audit_platform`` 即使被
点名也不放行；没设环境变量时只认快照库前缀。两个守卫都在任何连接之前判定，本文件不连库。
"""
from __future__ import annotations

import pytest

from tests.formula_hub._lineage_fixtures import assert_ddl_allowed
from tests.formula_hub._pg_harness import (
    DISPOSABLE_DB_ENV,
    SNAPSHOT_GUARD_TEXT,
    assert_snapshot_database,
    is_disposable_database,
)

CASES = [
    # (库名, GT_PG_DISPOSABLE_DB, 是否放行)
    ("fh_snap_202610300255", None, True),
    ("fh_snap_202610300255", "test_audit", True),
    ("test_audit", None, False),
    ("test_audit", "", False),
    ("test_audit", "test_audit", True),
    ("test_audit", " test_audit ", True),
    ("test_audit_2", "test_audit", False),  # 精确点名，不是前缀
    ("audit_test", "test_audit", False),
    ("audit_platform", None, False),
    ("audit_platform", "audit_platform", False),  # 共享库点名也不放行
    ("", "test_audit", False),
]


def _url(name: str) -> str:
    return f"postgresql+asyncpg://postgres:x@localhost:1/{name}"


def _set_env(monkeypatch, name: str, declared: str | None) -> None:
    monkeypatch.setenv("DATABASE_URL", _url(name))
    if declared is None:
        monkeypatch.delenv(DISPOSABLE_DB_ENV, raising=False)
    else:
        monkeypatch.setenv(DISPOSABLE_DB_ENV, declared)


@pytest.mark.parametrize(("name", "declared", "allowed"), CASES)
def test_is_disposable_database(monkeypatch, name, declared, allowed):
    _set_env(monkeypatch, name, declared)
    assert is_disposable_database(name) is allowed


@pytest.mark.parametrize(("name", "declared", "allowed"), CASES)
def test_committed_guard_follows_predicate(monkeypatch, name, declared, allowed):
    _set_env(monkeypatch, name, declared)
    if allowed:
        assert assert_snapshot_database() == name
        return
    with pytest.raises(pytest.fail.Exception, match=SNAPSHOT_GUARD_TEXT) as refused:
        assert_snapshot_database()
    assert f"当前库名 {name or '未知'}" in str(refused.value)


@pytest.mark.parametrize(("name", "declared", "allowed"), CASES)
def test_ddl_guard_follows_predicate(monkeypatch, name, declared, allowed):
    _set_env(monkeypatch, name, declared)
    if allowed:
        assert assert_ddl_allowed() is None
        return
    with pytest.raises(pytest.fail.Exception, match="含 DDL 的用例只连快照库") as refused:
        assert_ddl_allowed()
    assert f"当前库名 {name or '未知'}" in str(refused.value)
