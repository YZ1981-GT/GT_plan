"""回收站：底稿两层恢复、禁止彻底删除、项目鉴权（spec procedure-trim-generation-delegation-chain 需求 3.5 / 任务 10）。

真实路由 + SQLite 真 ORM。原先回收站全部端点只校验登录：任何人可列出 / 恢复 / 删除任何项目的数据；底稿按
working_paper 列出（没有编码列，只显示 id 前 8 位）、恢复只复活一层、彻底删除会撞外键。
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

import app.models  # noqa: E402, F401
from app.core.database import get_db  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.models.base import Base, PermissionLevel, ProjectStatus, ProjectUserRole, UserRole  # noqa: E402
from app.models.core import Project, ProjectUser, User  # noqa: E402
from app.models.procedure_models import ProcedureInstance  # noqa: E402
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType, WpStatus  # noqa: E402
from app.routers import recycle_bin  # noqa: E402
from app.services.workpaper_recycle_service import RECYCLE_LINEAGE_KEY  # noqa: E402

pytestmark = pytest.mark.asyncio


def _user(name: str, role=UserRole.auditor) -> User:
    return User(id=uuid.uuid4(), username=name, email=f"{name}@example.com", hashed_password="x", role=role,
                is_active=True)


def _project(name: str) -> Project:
    return Project(id=uuid.uuid4(), name=name, client_name=name, status=ProjectStatus.execution,
                   template_type="soe", report_scope="standalone", audit_year=2025)


@pytest.fixture
async def world():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as db:
        users = {k: _user(f"rb_{k}") for k in ("editor", "reader", "outsider")}
        users["admin"] = _user("rb_admin", UserRole.admin)
        mine, other = _project("【测试】回收站甲"), _project("【测试】回收站乙")
        db.add_all([*users.values(), mine, other])
        await db.flush()
        db.add_all([
            ProjectUser(project_id=mine.id, user_id=users["editor"].id, role=ProjectUserRole.auditor,
                        permission_level=PermissionLevel.edit),
            ProjectUser(project_id=mine.id, user_id=users["reader"].id, role=ProjectUserRole.readonly,
                        permission_level=PermissionLevel.readonly),
            ProcedureInstance(project_id=mine.id, audit_cycle="H", procedure_code="H3", procedure_name="H3",
                              status="not_applicable", wp_code="H3"),
        ])
        ids = {}
        for pid, code, kind in ((mine.id, "H3", "trim"), (mine.id, "E2", "manual"), (mine.id, "E3", "manual"),
                                (other.id, "Z1", "manual")):
            idx = WpIndex(project_id=pid, wp_code=code, wp_name=f"底稿{code}", audit_cycle=code[0],
                          status=WpStatus.not_started, is_deleted=True,
                          cross_ref_codes={RECYCLE_LINEAGE_KEY: [{"action": "recycled", "kind": kind}]})
            db.add(idx)
            await db.flush()
            db.add(WorkingPaper(project_id=pid, wp_index_id=idx.id, file_path="", is_deleted=True,
                                source_type=WpSourceType.template, file_version=1))
            ids[code] = idx.id
        await db.commit()

        current = {"user": users["editor"]}
        api = FastAPI()
        api.include_router(recycle_bin.router)

        async def _db():
            yield db

        async def _current() -> User:
            return current["user"]

        api.dependency_overrides[get_db] = _db
        api.dependency_overrides[get_current_user] = _current
        async with AsyncClient(transport=ASGITransport(app=api), base_url="http://rb") as http:
            yield {"http": http, "db": db, "ids": ids, "users": users, "current": current, "mine": mine.id}
    await engine.dispose()


async def _layers(world, code) -> tuple[bool, bool]:
    idx = (await world["db"].execute(sa.select(WpIndex).where(WpIndex.id == world["ids"][code]))).scalar_one()
    wp = (await world["db"].execute(sa.select(WorkingPaper).where(WorkingPaper.wp_index_id == idx.id))).scalar_one()
    await world["db"].refresh(idx)
    await world["db"].refresh(wp)
    return idx.is_deleted, wp.is_deleted


async def test_list_and_stats_only_member_projects(world):
    r = await world["http"].get("/api/recycle-bin", params={"item_type": "working_paper"})
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert sorted(i["name"] for i in items) == ["E2 底稿E2", "E3 底稿E3", "H3 底稿H3"], "名称 = 编码 + 底稿名，乙项目不可见"
    assert all(i["purgeable"] is False and i["type"] == "working_paper" for i in items)
    stats = (await world["http"].get("/api/recycle-bin/stats")).json()
    assert stats["by_type"]["working_paper"]["count"] == 3 and stats["total"] == 3
    world["current"]["user"] = world["users"]["outsider"]
    assert (await world["http"].get("/api/recycle-bin")).json()["items"] == []
    world["current"]["user"] = world["users"]["admin"]
    assert (await world["http"].get("/api/recycle-bin/stats")).json()["by_type"]["working_paper"]["count"] == 4


async def test_list_shows_who_deleted_the_workpaper(world):
    """「删除人」取回收站去向记录最后一条「移入」的操作人（人员档案姓名优先，回退用户名）。

    spec procedure-chain-followup-closure R3.2：列表项原先没有删除人，回收站「删除人」恒空。记录里没有操作人的
    （夹具里的旧记录）留空，不拿别的字段冒充。
    """
    from app.models.staff_models import StaffMember

    db = world["db"]
    editor = world["users"]["editor"]
    db.add(StaffMember(name="编制人甲", user_id=editor.id))
    e2 = (await db.execute(sa.select(WpIndex).where(WpIndex.id == world["ids"]["E2"]))).scalar_one()
    e2.cross_ref_codes = {RECYCLE_LINEAGE_KEY: [{"action": "recycled", "kind": "manual",
                                                 "actor": str(editor.id)}]}
    await db.commit()
    items = (await world["http"].get("/api/recycle-bin", params={"item_type": "working_paper"})).json()["items"]
    by_name = {i["name"]: i for i in items}
    assert by_name["E2 底稿E2"]["deleted_by"] == str(editor.id)
    assert by_name["E2 底稿E2"]["deleted_by_name"] == "编制人甲"
    assert by_name["E3 底稿E3"]["deleted_by"] is None and by_name["E3 底稿E3"]["deleted_by_name"] is None


async def test_deleting_a_project_records_who_and_when(world):
    """删除项目记删除人与删除时间，回收站列出删除人；从回收站恢复后清掉删除时间。"""
    from app.routers import project_wizard

    db = world["db"]
    admin = world["users"]["admin"]
    world["current"]["user"] = admin
    target = _project("【测试】回收站丙")
    db.add(target)
    await db.commit()
    api = FastAPI()
    api.include_router(project_wizard.router)

    async def _db():
        yield db

    async def _admin() -> User:
        return admin

    api.dependency_overrides[get_db] = _db
    api.dependency_overrides[get_current_user] = _admin
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://pw") as http:
        r = await http.delete(f"/api/projects/{target.id}")
    assert r.status_code == 200, r.text
    await db.refresh(target)
    assert target.is_deleted and target.deleted_at is not None and target.updated_by == admin.id
    items = (await world["http"].get("/api/recycle-bin", params={"item_type": "project"})).json()["items"]
    [item] = [i for i in items if i["id"] == str(target.id)]
    assert item["deleted_by"] == str(admin.id) and item["deleted_by_name"] == "rb_admin"
    assert item["deleted_at"] is not None


async def test_restore_workpaper_two_layers_with_project_auth(world):
    url = "/api/recycle-bin/working_paper/{}/restore"
    r = await world["http"].post(url.format(world["ids"]["E2"]))
    assert r.status_code == 200, r.text
    assert await _layers(world, "E2") == (False, False), "两层一起恢复"
    world["current"]["user"] = world["users"]["reader"]
    assert (await world["http"].post(url.format(world["ids"]["E3"]))).status_code == 403, "只读成员不能恢复"
    world["current"]["user"] = world["users"]["editor"]
    assert (await world["http"].post(url.format(world["ids"]["Z1"]))).status_code == 403, "不是乙项目成员"
    assert await _layers(world, "E3") == (True, True) and await _layers(world, "Z1") == (True, True)


async def test_still_trimmed_workpaper_cannot_be_restored_directly(world):
    r = await world["http"].post(f"/api/recycle-bin/working_paper/{world['ids']['H3']}/restore")
    assert r.status_code == 409, r.text
    assert "程序裁剪" in r.text and await _layers(world, "H3") == (True, True)


async def test_workpaper_purge_forbidden_and_empty_admin_only(world):
    r = await world["http"].delete(f"/api/recycle-bin/working_paper/{world['ids']['E2']}")
    assert r.status_code == 409 and "不支持彻底删除" in r.text
    r = await world["http"].post("/api/recycle-bin/batch-delete", params={"item_type": "working_paper"},
                                 json={"ids": [str(world["ids"]["E2"])]})
    assert r.status_code == 409
    assert (await world["http"].post("/api/recycle-bin/empty")).status_code == 403
    world["current"]["user"] = world["users"]["admin"]
    r = await world["http"].post("/api/recycle-bin/empty", params={"item_type": "working_paper"})
    assert r.status_code == 409 and "不支持彻底删除" in r.text, "按类型清空底稿同样不允许（管理员也不行）"
    assert (await world["http"].post("/api/recycle-bin/empty")).status_code == 200
    assert await _layers(world, "E2") == (True, True), "清空不清除底稿（两层软删保留）"
    assert (await world["db"].execute(sa.select(sa.func.count()).select_from(WpIndex))).scalar_one() == 4


async def test_other_recyclable_rows_use_updated_by_as_deleted_by():
    """非底稿类型没有回收轨迹时，沿用删除路径写入的 updated_by。"""
    from types import SimpleNamespace
    from app.routers.recycle_bin import _deleted_by

    actor = uuid.uuid4()
    assert _deleted_by("adjustment", SimpleNamespace(updated_by=actor)) == str(actor)
    assert _deleted_by("attachment", SimpleNamespace(updated_by=None)) is None
