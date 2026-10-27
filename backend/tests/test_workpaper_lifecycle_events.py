"""底稿生命周期领域事件（spec procedure-chain-hardening-and-java-contracts R18）—— SQLite 真 ORM，开外键检查。

移入 / 恢复回收站原先只记在 ``wp_index.cross_ref_codes["_recycle_lineage"]``（JSON，随行可改、不能按事件查询）。
现在同事务另写一条只追加事件；旧 JSON 照写（兼容）；回收站「删除人」先读最近一条事件，没有再回退 JSON。
事件表还没建（开发服热重载不跑迁移）时移入 / 恢复照常完成、只记警告；别的写入错误照常抛。
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

import app.models  # noqa: E402, F401
from app.core.database import get_db  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.models.base import Base, PermissionLevel, ProjectStatus, ProjectUserRole, UserRole  # noqa: E402
from app.models.core import Project, ProjectUser, User  # noqa: E402
from app.models.workpaper_lifecycle_models import WorkpaperLifecycleEvent  # noqa: E402
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType, WpStatus  # noqa: E402
from app.routers import recycle_bin  # noqa: E402
from app.services import workpaper_recycle_service as svc  # noqa: E402

from tests._sqlite_fk import enable_sqlite_foreign_keys  # noqa: E402

pytestmark = pytest.mark.asyncio


def _user(name: str, role=UserRole.auditor) -> User:
    return User(id=uuid.uuid4(), username=name, email=f"{name}@example.com", hashed_password="x", role=role,
                is_active=True)


@pytest.fixture
async def world(monkeypatch):
    epochs: list[tuple] = []

    async def _no_epoch(db, project_id, action, codes, actor_user_id, request_id):  # 可见性纪元不是本文件的对象
        epochs.append((action, list(codes)))

    monkeypatch.setattr(svc, "_bump_epoch", _no_epoch)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    enable_sqlite_foreign_keys(engine)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as db:
        editor, admin = _user("lc_editor"), _user("lc_admin", UserRole.admin)
        project = Project(id=uuid.uuid4(), name="【测试】生命周期", client_name="【测试】生命周期",
                          status=ProjectStatus.execution, template_type="soe", report_scope="standalone",
                          audit_year=2025)
        db.add_all([editor, admin, project])
        await db.flush()
        db.add(ProjectUser(project_id=project.id, user_id=editor.id, role=ProjectUserRole.auditor,
                           permission_level=PermissionLevel.edit))
        ids: dict[str, uuid.UUID] = {}
        papers: dict[str, uuid.UUID] = {}
        for code, deleted, lineage in (("E1", False, None), ("E2", False, None),
                                       ("E3", True, [{"action": "recycled", "kind": "manual",
                                                      "actor": str(admin.id)}])):
            idx = WpIndex(project_id=project.id, wp_code=code, wp_name=f"底稿{code}", audit_cycle="E",
                          status=WpStatus.not_started, is_deleted=deleted,
                          cross_ref_codes={svc.RECYCLE_LINEAGE_KEY: lineage} if lineage else None)
            db.add(idx)
            await db.flush()
            wp = WorkingPaper(project_id=project.id, wp_index_id=idx.id, file_path="", is_deleted=deleted,
                              source_type=WpSourceType.template, file_version=1)
            db.add(wp)
            await db.flush()
            ids[code], papers[code] = idx.id, wp.id
        await db.commit()

        current = {"user": editor}
        api = FastAPI()
        api.include_router(recycle_bin.router)

        async def _db():
            yield db

        async def _current() -> User:
            return current["user"]

        api.dependency_overrides[get_db] = _db
        api.dependency_overrides[get_current_user] = _current
        async with AsyncClient(transport=ASGITransport(app=api), base_url="http://lc") as http:
            yield {"db": db, "http": http, "pid": project.id, "editor": editor, "admin": admin, "ids": ids,
                   "papers": papers, "current": current, "engine": engine, "epochs": epochs}
    await engine.dispose()


async def _events(db) -> list[WorkpaperLifecycleEvent]:
    return list((await db.execute(sa.select(WorkpaperLifecycleEvent)
                                  .order_by(WorkpaperLifecycleEvent.created_at))).scalars())


async def _deleted_by(world) -> dict[str, str | None]:
    r = await world["http"].get("/api/recycle-bin", params={"item_type": "working_paper"})
    assert r.status_code == 200, r.text
    return {i["name"].split()[0]: i["deleted_by"] for i in r.json()["items"]}


async def test_move_and_restore_write_events_and_keep_lineage(world):
    db, pid, editor, admin = world["db"], world["pid"], world["editor"], world["admin"]
    moved = await svc.move_to_recycle_bin(db, pid, ["E1", "E2"], kind=svc.KIND_TRIM, reason="程序裁剪：E1",
                                          actor_user_id=editor.id, trim_codes={"E1": ["E1"]}, request_id="req-1")
    await db.commit()
    assert moved == ["E1", "E2"]
    rec = await _events(db)
    assert [(e.wp_code, e.event_type, e.kind, e.reason, e.actor_user_id, e.request_id) for e in rec] == [
        ("E1", "recycled", "trim", "程序裁剪：E1", editor.id, "req-1"),
        ("E2", "recycled", "trim", "程序裁剪：E1", editor.id, "req-1"),
    ]
    assert rec[0].trim_codes == ["E1"] and rec[1].trim_codes == []
    assert rec[0].working_paper_ids == [str(world["papers"]["E1"])]
    assert rec[0].project_id == pid and rec[0].wp_index_id == world["ids"]["E1"]
    # 旧 JSON 去向记录照写（兼容读取方）
    e1 = (await db.execute(sa.select(WpIndex).where(WpIndex.id == world["ids"]["E1"]))).scalar_one()
    assert [x["action"] for x in svc.read_lineage(e1)] == ["recycled"]

    restored = await svc.restore_from_recycle_bin(db, pid, ["E1"], kind=None, reason="从回收站恢复",
                                                  actor_user_id=admin.id, request_id="req-2")
    await db.commit()
    assert restored == ["E1"]
    last = (await _events(db))[-1]
    assert (last.wp_code, last.event_type, last.kind, last.actor_user_id, last.request_id) == (
        "E1", "restored", "trim", admin.id, "req-2"), "不限原因恢复时记最后一次移入的原因类别"
    assert world["epochs"] == [("workpaper_recycled", ["E1", "E2"]), ("workpaper_restored", ["E1"])]


async def test_recycle_bin_deleted_by_reads_events_then_lineage(world):
    db, pid, editor, admin = world["db"], world["pid"], world["editor"], world["admin"]
    await svc.move_to_recycle_bin(db, pid, ["E1", "E2"], kind="manual", reason="手工删除", actor_user_id=editor.id)
    await svc.restore_from_recycle_bin(db, pid, ["E1"], kind=None, reason="恢复", actor_user_id=editor.id)
    await svc.move_to_recycle_bin(db, pid, ["E1"], kind="manual", reason="再删", actor_user_id=admin.id)
    # 去向 JSON 被改写（JSON 随行可改）：事件仍记着真实操作人 ⇒ 以事件为准
    e2 = (await db.execute(sa.select(WpIndex).where(WpIndex.id == world["ids"]["E2"]))).scalar_one()
    e2.cross_ref_codes = {svc.RECYCLE_LINEAGE_KEY: [{"action": "recycled", "kind": "manual", "actor": str(admin.id)}]}
    await db.commit()
    world["current"]["user"] = admin
    by_code = await _deleted_by(world)
    assert by_code["E1"] == str(admin.id), "最近一条事件（再次移入）的操作人"
    assert by_code["E2"] == str(editor.id), "事件优先于去向 JSON"
    assert by_code["E3"] == str(admin.id), "没有事件的旧数据回退去向 JSON"


async def test_latest_recycle_actors_only_counts_latest_recycled_event(world):
    db, pid, editor, admin = world["db"], world["pid"], world["editor"], world["admin"]
    t0 = datetime.now(timezone.utc)
    a, b = world["ids"]["E1"], world["ids"]["E2"]

    def ev(wid, code, kind, who, dt):
        return WorkpaperLifecycleEvent(project_id=pid, wp_index_id=wid, wp_code=code, event_type=kind,
                                       actor_user_id=who, created_at=t0 + timedelta(milliseconds=dt))

    db.add_all([ev(a, "E1", "recycled", editor.id, 1), ev(a, "E1", "restored", admin.id, 2),
                ev(b, "E2", "recycled", editor.id, 1), ev(b, "E2", "recycled", None, 3),
                ev(b, "E2", "restored", admin.id, 2)])
    await db.commit()
    got = await svc.latest_recycle_actors(db, [a, b, world["ids"]["E3"]])
    assert got == {b: None}, "E1 最近是恢复 ⇒ 不在结果（回退 JSON）；E2 最近是移入（无操作人）；E3 无事件"


async def test_missing_events_table_degrades_without_failing(world, caplog):
    """迁移 V207 未落（开发服热重载不跑迁移）：移入 / 恢复照常完成、去向 JSON 照写，只记一条警告；回收站回退 JSON。"""
    db, pid, editor = world["db"], world["pid"], world["editor"]
    async with world["engine"].begin() as conn:
        await conn.execute(sa.text("DROP TABLE workpaper_lifecycle_events"))
    with caplog.at_level(logging.WARNING, logger=svc.logger.name):
        moved = await svc.move_to_recycle_bin(db, pid, ["E1"], kind="manual", reason="手工删除",
                                              actor_user_id=editor.id)
        await db.commit()
    assert moved == ["E1"]
    assert any("V207" in r.getMessage() for r in caplog.records)
    idx = (await db.execute(sa.select(WpIndex).where(WpIndex.id == world["ids"]["E1"]))).scalar_one()
    assert idx.is_deleted and svc.read_lineage(idx)[-1]["actor"] == str(editor.id)
    assert (await _deleted_by(world))["E1"] == str(editor.id)


async def test_other_event_write_errors_are_not_swallowed(world, monkeypatch):
    """只有「表不存在」降级；别的写入错误（这里：必填列为空）照常抛，本次移入不生效。"""
    db, pid, editor = world["db"], world["pid"], world["editor"]
    real = svc._event

    def broken(*a, **kw):
        e = real(*a, **kw)
        e.wp_code = None
        return e

    monkeypatch.setattr(svc, "_event", broken)
    with pytest.raises(IntegrityError):
        await svc.move_to_recycle_bin(db, pid, ["E1"], kind="manual", reason="手工删除", actor_user_id=editor.id)
    await db.rollback()
    idx = (await db.execute(sa.select(WpIndex).where(WpIndex.id == world["ids"]["E1"]))).scalar_one()
    assert idx.is_deleted is False
    assert await _events(db) == []


async def test_event_project_must_exist_with_sqlite_foreign_keys(world):
    """开了外键检查：事件的项目必须存在（与 PG 一致；原先 SQLite 默认不查外键，错的引用照样能插）。"""
    db = world["db"]
    db.add(WorkpaperLifecycleEvent(project_id=uuid.uuid4(), wp_index_id=uuid.uuid4(), wp_code="X1",
                                   event_type="recycled", created_at=datetime.now(timezone.utc)))
    with pytest.raises(IntegrityError):
        await db.flush()
    await db.rollback()
