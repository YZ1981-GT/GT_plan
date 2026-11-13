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
from app.models.archive_models import ArchiveJob
from app.models.base import ProjectStatus
from app.models.core import Project
from app.services.acnr import catalog_snapshot_gc as gc
from app.services.acnr import project_registry_lock
from app.services.acnr import snapshot_lifecycle_lock as lifecycle
from app.services.archive_orchestrator import ArchiveOrchestrator

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


async def test_archive_transaction_lock_makes_concurrent_gc_fail_closed(tmp_path, monkeypatch):
    """归档事务持锁期间，另一连接的 GC 必须零删除；事务结束后同一候选才可清理。

    这是需求 7.4「只删除未被任何项目锁定」的并发证据。旧实现先查引用、关闭短会话再删文件，
    归档可在两步之间写入锁；本例用 PostgreSQL advisory lock 的真实跨连接互斥钉住共同锁。
    不写任何业务表，文件只在 pytest tmp_path。
    """
    assert settings.DATABASE_URL.startswith("postgresql"), settings.DATABASE_URL
    directory = tmp_path / "catalog_snapshots"
    directory.mkdir()
    _git(directory, "init", "-q")
    candidate = "20991231235959"
    (directory / f"{candidate}.json").write_text(
        json.dumps({"registry_version": candidate}), encoding="utf-8"
    )
    monkeypatch.setenv("ACNR_SNAPSHOTS_DIR", str(directory))

    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    import app.core.database as db_module
    monkeypatch.setattr(db_module, "async_session", maker)
    try:
        async with engine.connect() as holder:
            transaction = await holder.begin()
            try:
                assert await lifecycle.try_acquire_snapshot_lifecycle_lock(holder) == "acquired"
                # run_db_aware_gc 自开另一条数据库连接；同一把 advisory xact lock 应返回 busy。
                report = await gc.run_db_aware_gc(keep_recent=0)
                assert report["lifecycle_lock_status"] == "busy"
                assert report["reference_status"] == "unverifiable"
                assert report["deleted"] == []
                assert (directory / f"{candidate}.json").is_file()
            finally:
                await transaction.rollback()

        # 持锁事务结束后，证明 GC 不是恒不删除：引用集可验证、git 可验证为空，该散落快照被清理。
        report = await gc.run_db_aware_gc(keep_recent=0)
        assert report["lifecycle_lock_status"] == "acquired"
        assert report["reference_status"] == "verified"
        assert report["deleted"] == [candidate]
        assert not (directory / f"{candidate}.json").exists()
    finally:
        await engine.dispose()


async def test_real_project_lock_transaction_blocks_gc_then_becomes_persistent_reference(tmp_path, monkeypatch):
    """穿过真实 ``lock_project_registry``：未提交时 GC busy，提交后 GC 从项目表读到引用。

    测试项目会短暂提交到共享开发库（跨连接可见性所需），名称带【测试】，finally 中按主键硬删并复核。
    除 projects 这一行外不写业务表；快照只在 pytest tmp_path。
    """
    assert settings.DATABASE_URL.startswith("postgresql"), settings.DATABASE_URL
    directory = tmp_path / "catalog_snapshots"
    directory.mkdir()
    _git(directory, "init", "-q")
    candidate = "20991130235959"
    (directory / f"{candidate}.json").write_text(
        json.dumps({"registry_version": candidate}), encoding="utf-8"
    )
    monkeypatch.setenv("ACNR_SNAPSHOTS_DIR", str(directory))

    project_id = uuid.uuid4()
    project_name = f"【测试】ACNR 生命周期锁 {project_id}"
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    import app.core.database as db_module
    monkeypatch.setattr(db_module, "async_session", maker)
    try:
        async with maker() as setup:
            setup.add(Project(
                id=project_id,
                name=project_name,
                client_name=project_name,
                status=ProjectStatus.created,
                is_deleted=False,
            ))
            await setup.commit()

        async with maker() as archive_db:
            async with archive_db.begin():
                assert await project_registry_lock.lock_project_registry(
                    archive_db, project_id, version=candidate
                ) == candidate
                # 项目锁尚未提交，第二连接还读不到引用；共同锁必须使 GC busy 而不是按空引用删除。
                report = await gc.run_db_aware_gc(keep_recent=0)
                assert report["lifecycle_lock_status"] == "busy"
                assert report["deleted"] == []
                assert (directory / f"{candidate}.json").is_file()
            # begin 正常退出，项目版本锁与 advisory lock 同时提交 / 释放。

        report = await gc.run_db_aware_gc(keep_recent=0)
        assert report["lifecycle_lock_status"] == "acquired"
        assert report["reference_status"] == "verified"
        assert report["referenced_count"] >= 1
        assert report["deleted"] == []
        assert (directory / f"{candidate}.json").is_file(), "提交后的项目锁没有保护快照"
    finally:
        async with maker() as cleanup:
            await cleanup.execute(sa.delete(Project).where(Project.id == project_id))
            await cleanup.commit()
        async with maker() as verify:
            assert await verify.scalar(
                sa.select(sa.func.count()).select_from(Project).where(Project.id == project_id)
            ) == 0
        await engine.dispose()


async def test_real_advisory_sql_error_rolls_back_savepoint_and_failed_job_can_flush(tmp_path, monkeypatch):
    """真实 PG 让 advisory SQL 报错：SAVEPOINT 回滚后，编排器仍能写 failed job。

    第一轮语义审查指出：若锁 SQL 使外层事务 aborted，``_run`` 的失败 flush 会再报 500，稳定 409
    契约失效。本例把生产锁 SQL 替换成真实 ``SELECT 1 / 0``（故障在被测函数下一层），证明错误只
    回滚保存点；编排器随后成功 flush failed 状态并重抛 RegistryLockError。全部在外层事务回滚。
    """
    assert settings.DATABASE_URL.startswith("postgresql"), settings.DATABASE_URL
    directory = tmp_path / "catalog_snapshots"
    directory.mkdir()
    candidate = "20991031235959"
    (directory / f"{candidate}.json").write_text(
        json.dumps({"registry_version": candidate}), encoding="utf-8"
    )
    monkeypatch.setenv("ACNR_SNAPSHOTS_DIR", str(directory))

    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    project_id = uuid.uuid4()
    name = f"【测试】ACNR 锁 SQL 故障 {project_id}"
    real_text = sa.text
    try:
        async with engine.connect() as conn:
            outer = await conn.begin()
            maker = async_sessionmaker(
                bind=conn,
                class_=AsyncSession,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )
            try:
                async with maker() as db:
                    project = Project(
                        id=project_id,
                        name=name,
                        client_name=name,
                        status=ProjectStatus.created,
                        is_deleted=False,
                    )
                    job = ArchiveJob(
                        project_id=project_id,
                        status="running",
                        scope="final",
                        push_to_cloud=False,
                        purge_local=False,
                        section_progress={},
                    )
                    db.add(project)
                    await db.flush()
                    db.add(job)
                    await db.flush()

                    # 只替换 SQL 构造器的结果，生产 try/savepoint/错误映射代码原样执行。
                    monkeypatch.setattr(lifecycle.sa, "text", lambda _sql: real_text("SELECT 1 / 0"))

                    async def lock_step(_job):
                        await project_registry_lock.lock_project_registry(
                            db, project_id, version=candidate
                        )

                    orchestrator = ArchiveOrchestrator(db)
                    monkeypatch.setattr(orchestrator, "_build_steps", lambda *_args: [("lock", lock_step)])
                    with pytest.raises(project_registry_lock.RegistryLockError) as caught:
                        await orchestrator._run(job, start_from=0)

                    assert caught.value.code == "lock_failed"
                    assert job.status == "failed" and job.failed_section == "lock"
                    assert job.section_progress["lock"]["status"] == "failed"
                    # 关键反证：若 SQL 错误逃出 SAVEPOINT，下面两条都会报 InFailedSQLTransaction。
                    await db.flush()
                    assert await db.scalar(real_text("SELECT 42")) == 42
            finally:
                await outer.rollback()
        async with engine.connect() as check:
            assert await check.scalar(
                sa.select(sa.func.count()).select_from(Project).where(Project.id == project_id)
            ) == 0
            assert await check.scalar(
                sa.select(sa.func.count()).select_from(ArchiveJob).where(ArchiveJob.project_id == project_id)
            ) == 0
    finally:
        await engine.dispose()
