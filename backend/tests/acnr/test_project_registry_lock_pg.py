"""T18 真 PostgreSQL：两条归档写入路径与落库版本锁同事务，外层事务回滚。"""
from __future__ import annotations

from types import SimpleNamespace
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.base import ProjectStatus, ProjectType, UserRole
from app.models.core import Project, User
from app.models.phase13_models import WordExportTask
from app.services.acnr.catalog import get_catalog
from app.services.acnr.project_registry_lock import get_locked_version, unlock_project_registry
from app.services.archive_orchestrator import ArchiveOrchestrator
from app.services.deliverable_service import DeliverableService

pytestmark = pytest.mark.pg_only


def _project(pid: uuid.UUID, uid: uuid.UUID, suffix: str) -> Project:
    name = f"【测试】ACNR 归档 {suffix} {pid}"
    return Project(
        id=pid, name=name, client_name=name, project_type=ProjectType.annual,
        status=ProjectStatus.reporting, created_by=uid,
    )


async def test_both_archive_paths_persist_lock_and_rollback_all_rows():
    assert settings.DATABASE_URL.startswith("postgresql"), settings.DATABASE_URL
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    uid, orchestrator_pid, deliverable_pid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    version = get_catalog().registry_version
    try:
        async with engine.connect() as conn:
            outer = await conn.begin()
            maker = async_sessionmaker(
                bind=conn, class_=AsyncSession, expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )
            async with maker() as db:
                # created_by / project_id 是裸列、无 ORM relationship，SQLAlchemy 的 unit-of-work
                # 不知道 projects→users、word_export→projects 的插入依赖，一次 flush 的 insertmany
                # 分组顺序不保证 ⇒ 真 PG 上报 FK 违反。按依赖分三步 flush。
                db.add(User(
                    id=uid, username=f"acnr_{uid.hex[:12]}", email=f"acnr_{uid.hex[:12]}@test.invalid",
                    hashed_password="x", role=UserRole.admin,
                ))
                await db.flush()
                db.add_all([_project(orchestrator_pid, uid, "orchestrator"), _project(deliverable_pid, uid, "deliverable")])
                await db.flush()
                db.add(WordExportTask(
                    id=uuid.uuid4(), project_id=deliverable_pid, doc_type="financial_report",
                    status="confirmed", template_type="soe", created_by=uid,
                ))
                await db.flush()

                await ArchiveOrchestrator(db)._step_lock(SimpleNamespace(project_id=orchestrator_pid))
                first = await db.get(Project, orchestrator_pid)
                assert first.status == ProjectStatus.archived
                assert await get_locked_version(db, orchestrator_pid) == version

                count = await DeliverableService(db).archive_project_deliverables(
                    deliverable_pid, uid, 2025, force=True,
                )
                second = await db.get(Project, deliverable_pid)
                assert count == 1 and second.status == ProjectStatus.archived
                assert await get_locked_version(db, deliverable_pid) == version

                # 解除归档的持久锁逆操作：两列同清，服务只 flush，由外层事务决定提交。
                previous = await unlock_project_registry(db, orchestrator_pid)
                first.status = ProjectStatus.execution
                await db.flush()
                assert previous == version
                assert first.acnr_registry_version is None and first.acnr_registry_locked_at is None

            await outer.rollback()

        async with engine.connect() as check:
            count = await check.scalar(sa.select(sa.func.count()).select_from(Project).where(
                Project.id.in_([orchestrator_pid, deliverable_pid])
            ))
            assert count == 0
    finally:
        await engine.dispose()


# ─── T18 端到端：归档项目按锁定版本复现（R2-F7）────────────────────────────────
#
# Verify 原文要求：建【测试】项目经交付件归档真实路径归档 → 清缓存模拟重启 → 换目录 v2 →
# 仍按 v1；取消归档 → 按 v2；删 v1 快照 → 409 snapshot_missing；
# R2-F7「v1·v2 名称归属不同、锁定按 v1」一例。
#
# 做法：v1 / v2 两份合成快照只差同一个 cell 的 semantic_label。锁到 v1（显式传 version，
# 避开锁当前版本时的 release 哈希校验），把「当前目录」mock 成 v2。full_resolve 带归档项目
# 应读 v1 的语义名（不是 v2），证明锁定生效、归档可复现。resolver 读 _CATALOG_SNAPSHOTS_DIR
# （模块常量，monkeypatch），锁服务 verify_snapshot 读 ACNR_SNAPSHOTS_DIR（环境变量），两者
# 指向同一临时目录。

import json as _json
import os as _os
from pathlib import Path as _Path
from unittest.mock import patch as _patch

from app.services.acnr.catalog import CatalogIndex
from app.services.acnr.project_registry_lock import lock_project_registry
from app.services.acnr.resolver import (
    VersionNotFoundError,
    full_resolve,
    load_versioned_catalog,
)

_V1 = "20240101000000"
_V2 = "20250101000000"
_ADDR = "D2/D2-2/E100"


def _write_snapshot(dir_: _Path, version: str, label: str) -> None:
    data = {
        "version": "1",
        "registry_version": version,
        "sheets": [{
            "addr_id": "D2/D2-2", "sheet_code": "D2-2", "sheet_name": "明细表D2-2",
            "domain": "wp", "parent_wp_code": "D2", "cycle": "D", "sheet_name_aliases": [],
        }],
        "cells": [{
            "addr_id": _ADDR, "parent_addr_id": "D2/D2-2", "domain": "wp",
            "cell_address": "E100", "semantic_label": label,
            "formula_ref": "WP('D2','D2-2','E100')", "uri": "wp://D2/明细表D2-2#E100",
        }],
    }
    (dir_ / f"{version}.json").write_text(
        _json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8",
    )


async def test_archived_project_resolves_by_locked_version_not_current(tmp_path, monkeypatch):
    """R2-F7：归档锁 v1 → 按 v1 名称归属解析（v2 是当前目录、名称归属不同）；
    解锁 → 按 v2；删 v1 快照 → VersionNotFoundError（映射 409 snapshot_missing）。"""
    assert settings.DATABASE_URL.startswith("postgresql"), settings.DATABASE_URL

    snaps = tmp_path / "snaps"
    snaps.mkdir()
    _write_snapshot(snaps, _V1, "应收账款合计（v1）")
    _write_snapshot(snaps, _V2, "应收账款合计（v2）")

    # 锁服务 verify_snapshot 走 ACNR_SNAPSHOTS_DIR；resolver.load_versioned_catalog 走模块常量
    monkeypatch.setenv("ACNR_SNAPSHOTS_DIR", str(snaps))
    import app.services.acnr.resolver as _resolver_mod
    monkeypatch.setattr(_resolver_mod, "_CATALOG_SNAPSHOTS_DIR", snaps)
    load_versioned_catalog.cache_clear()

    # 「当前目录」= v2（名称归属与 v1 不同），用来证明锁定没有退回当前
    current_v2 = CatalogIndex(_json.loads((snaps / f"{_V2}.json").read_text(encoding="utf-8")))

    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    uid, pid = uuid.uuid4(), uuid.uuid4()
    try:
        async with engine.connect() as conn:
            outer = await conn.begin()
            maker = async_sessionmaker(
                bind=conn, class_=AsyncSession, expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )
            async with maker() as db:
                db.add(User(
                    id=uid, username=f"acnr_{uid.hex[:12]}", email=f"acnr_{uid.hex[:12]}@test.invalid",
                    hashed_password="x", role=UserRole.admin,
                ))
                await db.flush()
                db.add(_project(pid, uid, "reproduce"))
                await db.flush()

                # 显式锁到 v1（非当前版本 ⇒ verify_snapshot 只验快照存在 + 自洽，不校 release 哈希）
                locked = await lock_project_registry(db, pid, version=_V1)
                assert locked == _V1
                assert await get_locked_version(db, pid) == _V1

                with _patch("app.services.acnr.resolver.get_catalog", return_value=current_v2):
                    # 锁 v1 ⇒ 按 v1 的名称归属解析（不是当前 v2）
                    r1 = await full_resolve(addr_id=_ADDR, project_id=str(pid), db=db, verify_existence=False)
                    assert r1.found and r1.semantic_label == "应收账款合计（v1）", r1
                    assert r1.version_lock_checked is True

                    # 取消归档（解锁）⇒ 按当前 v2 解析
                    db.info.pop("acnr_locked_version", None)  # 清请求级记忆，模拟新请求
                    prev = await unlock_project_registry(db, pid)
                    assert prev == _V1
                    r2 = await full_resolve(addr_id=_ADDR, project_id=str(pid), db=db, verify_existence=False)
                    assert r2.found and r2.semantic_label == "应收账款合计（v2）", r2

                    # 重新锁 v1，删 v1 快照 ⇒ full_resolve fail-closed 抛 VersionNotFoundError
                    db.info.pop("acnr_locked_version", None)
                    await lock_project_registry(db, pid, version=_V1)
                    (snaps / f"{_V1}.json").unlink()
                    load_versioned_catalog.cache_clear()
                    db.info.pop("acnr_locked_version", None)
                    with pytest.raises(VersionNotFoundError) as exc:
                        await full_resolve(addr_id=_ADDR, project_id=str(pid), db=db, verify_existence=False)
                    assert exc.value.version == _V1

            await outer.rollback()

        async with engine.connect() as check:
            count = await check.scalar(
                sa.select(sa.func.count()).select_from(Project).where(Project.id == pid)
            )
            assert count == 0
    finally:
        load_versioned_catalog.cache_clear()
        await engine.dispose()
