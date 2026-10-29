"""T19 真 PostgreSQL：运行时快照清理读项目表落库的版本锁（含回收站项目），整体在外层事务内回滚。

夹具：外层事务内建一个【测试】项目（已归档、已移入回收站），锁定一个不在最近 keep_recent=10 份之内的旧版本；
快照目录是临时 git 仓库：12 份已登记，另有被锁的旧快照与未被锁的旧快照各一份（都未登记）。
`app.core.database.async_session` 换成绑定本连接的会话工厂，于是不带会话的两个入口（启动任务、
`gc_snapshots.py`）自开的短会话读得到外层事务里的这一行。
"""
from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core import startup_registry
from app.core.config import settings
from app.models.base import ProjectStatus
from app.models.core import Project
from app.services.acnr import catalog_snapshot_gc as gc

pytestmark = pytest.mark.pg_only

_COMMITTED = [f"202610{day:02d}000000" for day in range(1, 13)]
_LOCKED_OLD = "20250101000000"
_UNREFERENCED_OLD = "20250202000000"


def _git(directory: Path, *args: str) -> None:
    env = {k: v for k, v in os.environ.items() if k not in gc._GIT_REDIRECT_ENV}
    subprocess.run(["git", "-C", str(directory), *args], check=True, capture_output=True, env=env)


def _snapshot_repo(tmp_path: Path) -> Path:
    directory = tmp_path / "catalog_snapshots"
    directory.mkdir()
    _git(directory, "init", "-q")
    for version in _COMMITTED + [_LOCKED_OLD, _UNREFERENCED_OLD]:
        (directory / f"{version}.json").write_text(json.dumps({"registry_version": version}), encoding="utf-8")
    _git(directory, "add", "--", *[f"{v}.json" for v in _COMMITTED])
    return directory


def _remaining(directory: Path) -> list[str]:
    return sorted(p.stem for p in directory.glob("*.json"))


@contextlib.asynccontextmanager
async def _locked_project_world(tmp_path: Path, monkeypatch, *, abort_transaction: bool = False):
    assert settings.DATABASE_URL.startswith("postgresql"), settings.DATABASE_URL
    directory = _snapshot_repo(tmp_path)
    monkeypatch.setenv("ACNR_SNAPSHOTS_DIR", str(directory))
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    project_id = uuid.uuid4()
    name = f"【测试】ACNR GC {project_id}"
    try:
        async with engine.connect() as conn:
            outer = await conn.begin()
            try:
                maker = async_sessionmaker(
                    bind=conn, class_=AsyncSession, expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                )
                async with maker() as db:
                    db.add(Project(
                        id=project_id, name=name, client_name=name, status=ProjectStatus.archived,
                        acnr_registry_version=_LOCKED_OLD, is_deleted=True,
                    ))
                    # create_savepoint 模式下 commit 只释放保存点，这一行留在外层事务里；
                    # 不 commit 就关会话，保存点回滚、这一行随之消失
                    await db.commit()
                if abort_transaction:
                    # 真实的查库失败：外层事务进入 aborted 状态，之后的语句（含保存点）都会报错
                    with pytest.raises(sa.exc.DBAPIError):
                        await conn.execute(sa.text("SELECT 1 / 0"))
                import app.core.database as db_module
                monkeypatch.setattr(db_module, "async_session", maker)
                yield directory
            finally:
                await outer.rollback()
        async with engine.connect() as check:
            count = await check.scalar(
                sa.select(sa.func.count()).select_from(Project).where(Project.id == project_id))
        assert count == 0, "外层事务没有回滚干净"
    finally:
        await engine.dispose()


async def test_startup_task_keeps_snapshot_locked_by_recycle_bin_project(tmp_path, monkeypatch):
    """启动任务（session=None 自开短会话）读到回收站项目的锁：被锁旧快照保住，未被锁且未登记的旧快照删掉。"""
    async with _locked_project_world(tmp_path, monkeypatch) as directory:
        await startup_registry._task_acnr_catalog_snapshot_gc(None)
        remaining = _remaining(directory)
    assert remaining == sorted(_COMMITTED + [_LOCKED_OLD]), remaining


async def test_gc_cli_reads_same_lock_and_dry_run_deletes_nothing(tmp_path, monkeypatch, capsys):
    """gc_snapshots.py 与启动任务同一入口：预览模式报出同一份待删清单，文件一个不动。"""
    from scripts.acnr import gc_snapshots

    async with _locked_project_world(tmp_path, monkeypatch) as directory:
        monkeypatch.setattr(sys, "argv", ["gc_snapshots", "--dry-run"])
        assert await gc_snapshots._main() == 0
        remaining = _remaining(directory)
    out = capsys.readouterr().out
    assert "reference_status  = verified" in out, out
    assert f"deleted           = 1 ['{_UNREFERENCED_OLD}']" in out, out
    assert remaining == sorted(_COMMITTED + [_LOCKED_OLD, _UNREFERENCED_OLD]), remaining


async def test_pg_query_failure_deletes_nothing(tmp_path, monkeypatch):
    """真实查库失败（事务已 aborted，自开会话的保存点即报错）→ 引用集证实不了 → 一个都不删。"""
    async with _locked_project_world(tmp_path, monkeypatch, abort_transaction=True) as directory:
        await startup_registry._task_acnr_catalog_snapshot_gc(None)
        report = await gc.run_db_aware_gc(keep_recent=10, dry_run=True)
        remaining = _remaining(directory)
    assert report["reference_status"] == "unverifiable" and report["deleted"] == []
    assert remaining == sorted(_COMMITTED + [_LOCKED_OLD, _UNREFERENCED_OLD]), remaining
