"""T17 守卫：版本锁的迁移 / ORM / 服务三层一致 + 锁定行为（design §8.3 / 需求 7.1~7.2）。

判据：
1. **三层一致**：迁移 V214 加的两列、配对回滚 R214 删的两列、ORM 的两个字段，列名与类型逐项对上
   （VARCHAR(14) ↔ String(14)、TIMESTAMPTZ ↔ DateTime(timezone=True)）。变异：ORM 类型改成
   `String` 或去掉 `timezone=True` → 本文件红。
2. **版本号形态单一来源**：模型层正则、服务层正则、`catalog_contract.REGISTRY_VERSION_PATTERN`
   三处逐字相同；模型层 `@validates` 真的拦得住非法形态（不是只写了注释）。
3. **锁之前先验快照**：快照不在 → `snapshot_missing`；快照内版本号与文件名不符 → `snapshot_invalid`；
   版本号形态不对 → `lock_failed`；三者都**不写库**。
4. **异常继承**：`RegistryLockError` 是 `CatalogLoadError` 的子类，且**不是** ValueError
   （归档路由对 ValueError 有 400 兜底，会抢先吃掉目录类错误，R2-N4）。
5. **行为（SQLite 真 ORM）**：锁 → 幂等重复锁不改时间戳 → 换锁被拒 → 解锁清两列 →
   `get_locked_version` 请求级记忆；存量 NULL 即未锁定。
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

import app.models  # noqa: E402, F401
from app.models.base import Base, ProjectStatus  # noqa: E402
from app.models.core import Project, User, _ACNR_REGISTRY_VERSION_RE  # noqa: E402
from app.services.acnr import project_registry_lock as prl  # noqa: E402
from app.services.acnr.catalog import CatalogLoadError  # noqa: E402
from app.services.acnr.catalog_contract import REGISTRY_VERSION_PATTERN  # noqa: E402

_BACKEND = Path(__file__).resolve().parents[2]
_MIG = _BACKEND / "migrations"
_TABLES = [User.__table__, Project.__table__]
_COLUMNS = ("acnr_registry_version", "acnr_registry_locked_at")


# ─── 1. 三层一致 ───────────────────────────────────────────────────────────


def _migration_text(prefix: str) -> str:
    hits = sorted(_MIG.glob(f"{prefix}*__*acnr_project_registry_lock.sql"))
    assert len(hits) == 1, f"{prefix} 迁移应恰有一个，实际 {[p.name for p in hits]}"
    return hits[0].read_text(encoding="utf-8")


def test_migration_adds_both_columns_with_declared_types() -> None:
    sql = _migration_text("V")
    assert re.search(r"ADD COLUMN IF NOT EXISTS\s+acnr_registry_version\s+VARCHAR\(14\)", sql), sql
    assert re.search(r"ADD COLUMN IF NOT EXISTS\s+acnr_registry_locked_at\s+TIMESTAMPTZ", sql), sql
    assert "ALTER TABLE projects" in sql


def test_rollback_migration_drops_both_columns() -> None:
    sql = _migration_text("R")
    for col in _COLUMNS:
        assert re.search(rf"DROP COLUMN IF EXISTS\s+{col}\b", sql), f"{col} 未在回滚里删除"


def test_migration_and_rollback_numbers_pair() -> None:
    v = sorted(_MIG.glob("V*__acnr_project_registry_lock.sql"))[0].name
    r = sorted(_MIG.glob("R*__*acnr_project_registry_lock.sql"))[0].name
    assert v[1:4] == r[1:4], f"迁移与回滚编号不配对：{v} / {r}"


def test_orm_columns_match_migration_types() -> None:
    """ORM 两列的类型与迁移声明逐项对上（类型写错即红）。"""
    cols = {c.name: c for c in Project.__table__.columns if c.name in _COLUMNS}
    assert set(cols) == set(_COLUMNS), f"ORM 缺列：{set(_COLUMNS) - set(cols)}"

    version = cols["acnr_registry_version"]
    assert version.type.__class__.__name__ == "String", version.type
    assert getattr(version.type, "length", None) == 14, f"VARCHAR 长度应为 14，实际 {version.type}"
    assert version.nullable is True, "未锁定即 NULL，不能非空"

    locked_at = cols["acnr_registry_locked_at"]
    assert locked_at.type.__class__.__name__ == "DateTime", locked_at.type
    assert getattr(locked_at.type, "timezone", False) is True, "TIMESTAMPTZ 必须带时区"
    assert locked_at.nullable is True


def test_orm_columns_have_no_default() -> None:
    """存量不回填：两列都不能有默认值 / 服务端默认值，否则旧项目会被当成已锁定。"""
    for name in _COLUMNS:
        col = Project.__table__.columns[name]
        assert col.default is None, f"{name} 不应有默认值"
        assert col.server_default is None, f"{name} 不应有服务端默认值"


# ─── 2. 版本号形态单一来源 ────────────────────────────────────────────────


def test_version_pattern_is_identical_in_three_places() -> None:
    assert _ACNR_REGISTRY_VERSION_RE.pattern == REGISTRY_VERSION_PATTERN, (
        _ACNR_REGISTRY_VERSION_RE.pattern, REGISTRY_VERSION_PATTERN)
    assert prl._VERSION_RE == REGISTRY_VERSION_PATTERN, (prl._VERSION_RE, REGISTRY_VERSION_PATTERN)


@pytest.mark.parametrize("bad", ["2026", "2026102907553", "202610290755330", "abcdefghijklmn",
                                 "2026-10-29 07:55", " 2026102907553a"])
def test_model_validator_rejects_bad_version(bad: str) -> None:
    project = Project()
    with pytest.raises(ValueError, match="14 位 UTC 时间戳"):
        project.acnr_registry_version = bad


def test_model_validator_accepts_none_and_14_digits() -> None:
    project = Project()
    project.acnr_registry_version = None
    assert project.acnr_registry_version is None
    project.acnr_registry_version = "20261029075533"
    assert project.acnr_registry_version == "20261029075533"
    project.acnr_registry_version = "  20261029075533  "  # 两端空白归一
    assert project.acnr_registry_version == "20261029075533"


# ─── 3~4. 快照校验与异常继承 ──────────────────────────────────────────────


def test_registry_lock_error_inherits_catalog_load_error_not_value_error() -> None:
    assert issubclass(prl.RegistryLockError, CatalogLoadError)
    assert not issubclass(prl.RegistryLockError, ValueError), (
        "继承 ValueError 会被归档路由的 400 兜底抢先吃掉（R2-N4）")


@pytest.fixture
def snapshots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """把快照目录指到临时目录，不碰仓库里的快照。"""
    monkeypatch.setenv("ACNR_SNAPSHOTS_DIR", str(tmp_path))
    return tmp_path


def test_verify_snapshot_missing(snapshots: Path) -> None:
    with pytest.raises(prl.RegistryLockError) as exc:
        prl.verify_snapshot("20261029075533")
    assert exc.value.code == "snapshot_missing"
    assert "快照缺失" in exc.value.message


def test_verify_snapshot_inner_version_mismatch(snapshots: Path) -> None:
    (snapshots / "20261029075533.json").write_text(
        json.dumps({"registry_version": "20260101000000"}), encoding="utf-8")
    with pytest.raises(prl.RegistryLockError) as exc:
        prl.verify_snapshot("20261029075533")
    assert exc.value.code == "snapshot_invalid"
    assert "与文件名不一致" in exc.value.message


def test_verify_snapshot_unparsable(snapshots: Path) -> None:
    (snapshots / "20261029075533.json").write_bytes(b"{ not json")
    with pytest.raises(prl.RegistryLockError) as exc:
        prl.verify_snapshot("20261029075533")
    assert exc.value.code == "snapshot_invalid"


@pytest.mark.parametrize("bad", ["", "2026", "2026102907553x"])
def test_verify_snapshot_rejects_bad_version_format(bad: str, snapshots: Path) -> None:
    with pytest.raises(prl.RegistryLockError) as exc:
        prl.verify_snapshot(bad)
    assert exc.value.code == "lock_failed"


def test_verify_snapshot_accepts_self_consistent_snapshot(snapshots: Path) -> None:
    (snapshots / "20260101000000.json").write_text(
        json.dumps({"registry_version": "20260101000000", "sheets": [], "cells": []}),
        encoding="utf-8")
    prl.verify_snapshot("20260101000000")  # 不抛即通过


def test_real_snapshots_all_verify() -> None:
    """仓库里每一份快照都能过校验（锁到任一历史版本都不会卡在校验上）。"""
    snaps = sorted((_BACKEND / "data" / "acnr" / "catalog_snapshots").glob("*.json"))
    assert snaps, "快照目录为空"
    for p in snaps:
        prl.verify_snapshot(p.stem)


# ─── 5. 锁定行为（SQLite 真 ORM）──────────────────────────────────────────


@pytest.fixture
async def db(snapshots: Path):
    (snapshots / "20260101000000.json").write_text(
        json.dumps({"registry_version": "20260101000000"}), encoding="utf-8")
    (snapshots / "20260202000000.json").write_text(
        json.dumps({"registry_version": "20260202000000"}), encoding="utf-8")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:",
                                 connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_TABLES)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _make_project(db: AsyncSession) -> uuid.UUID:
    pid = uuid.uuid4()
    db.add(Project(id=pid, name="【测试】版本锁", client_name="x", status=ProjectStatus.created))
    await db.flush()
    return pid


@pytest.mark.asyncio
async def test_lock_then_idempotent_then_refuse_relock(db: AsyncSession) -> None:
    pid = await _make_project(db)

    # 存量未锁定
    assert await prl.get_locked_version(db, pid) is None

    locked = await prl.lock_project_registry(db, pid, version="20260101000000")
    assert locked == "20260101000000"
    row = (await db.execute(
        Project.__table__.select().where(Project.id == pid))).mappings().one()
    assert row["acnr_registry_version"] == "20260101000000"
    first_at = row["acnr_registry_locked_at"]
    assert first_at is not None

    # 幂等：重复锁同一版本不改时间戳
    assert await prl.lock_project_registry(db, pid, version="20260101000000") == "20260101000000"
    again = (await db.execute(
        Project.__table__.select().where(Project.id == pid))).mappings().one()
    assert again["acnr_registry_locked_at"] == first_at

    # 换锁被拒（必须先解锁）
    with pytest.raises(prl.RegistryLockError) as exc:
        await prl.lock_project_registry(db, pid, version="20260202000000")
    assert exc.value.code == "lock_failed"
    assert "先取消归档" in exc.value.message
    still = (await db.execute(
        Project.__table__.select().where(Project.id == pid))).mappings().one()
    assert still["acnr_registry_version"] == "20260101000000", "换锁被拒后原锁必须原样"


@pytest.mark.asyncio
async def test_unlock_clears_both_columns(db: AsyncSession) -> None:
    pid = await _make_project(db)
    await prl.lock_project_registry(db, pid, version="20260101000000")

    previous = await prl.unlock_project_registry(db, pid)
    assert previous == "20260101000000"
    row = (await db.execute(
        Project.__table__.select().where(Project.id == pid))).mappings().one()
    assert row["acnr_registry_version"] is None
    assert row["acnr_registry_locked_at"] is None, "两列同写同清"
    assert await prl.get_locked_version(db, pid) is None

    # 解锁后可以重新锁到别的版本
    assert await prl.lock_project_registry(db, pid, version="20260202000000") == "20260202000000"


@pytest.mark.asyncio
async def test_unlock_on_unlocked_project_is_noop(db: AsyncSession) -> None:
    pid = await _make_project(db)
    assert await prl.unlock_project_registry(db, pid) is None


@pytest.mark.asyncio
async def test_lock_does_not_write_when_snapshot_missing(db: AsyncSession) -> None:
    pid = await _make_project(db)
    with pytest.raises(prl.RegistryLockError) as exc:
        await prl.lock_project_registry(db, pid, version="20269999000000")
    assert exc.value.code == "snapshot_missing"
    row = (await db.execute(
        Project.__table__.select().where(Project.id == pid))).mappings().one()
    assert row["acnr_registry_version"] is None, "校验不过不得落库"


@pytest.mark.asyncio
async def test_lock_unknown_project_fails(db: AsyncSession) -> None:
    with pytest.raises(prl.RegistryLockError) as exc:
        await prl.lock_project_registry(db, uuid.uuid4(), version="20260101000000")
    assert exc.value.code == "lock_failed"


@pytest.mark.asyncio
async def test_get_locked_version_memoizes_per_request(db: AsyncSession) -> None:
    """请求级记忆：第二次不再查库（把表改名也仍返回缓存值）。"""
    pid = await _make_project(db)
    await prl.lock_project_registry(db, pid, version="20260101000000")
    assert await prl.get_locked_version(db, pid) == "20260101000000"

    memo = db.info.get(prl._MEMO_KEY)
    assert memo and memo[str(pid)] == "20260101000000"

    memo[str(pid)] = "20260202000000"  # 篡改缓存证明读的是缓存
    assert await prl.get_locked_version(db, pid) == "20260202000000"
