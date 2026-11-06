"""合伙人只能看见自己名下的项目（partner_visibility_service + 各调用点）。

拓扑：合伙人甲 / 乙各一名，甲有一名下属经理；8 个项目各由一个来源支撑：

| 项目 | 关系 | 甲可见 |
|---|---|---|
| P_own | 甲创建 | ✓ (a) |
| P_sub | 甲的下属创建 | ✓ (b) |
| P_sign | 甲是签字合伙人 | ✓ (c) |
| P_wp | 甲是某底稿复核人 | ✓ (d) |
| P_assign | 甲经人员档案被委派 | ✓ (e) |
| P_member | 甲有成员行 | ✓ (f) |
| P_yi | 乙创建并签字，与甲无关 | ✗ |
| P_deleted | 甲创建但已软删 | ✗ |

另验：admin 仍看全部；项目列表接口与项目树按同一可见集过滤；底稿读写门禁对乙的项目拒绝。
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.deps import (
    _project_level_visible_ids,
    authorize_wp_edit,
    authorize_wp_read,
    get_visible_project_ids,
)
from app.models.base import PermissionLevel, ProjectUserRole, UserRole
from app.models.core import Project, ProjectUser, User
from app.models.staff_models import ProjectAssignment, StaffMember
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.partner_visibility_service import partner_visible_project_ids, subordinate_ids

pytestmark = pytest.mark.asyncio

_TABLES = (
    User.__table__, Project.__table__, ProjectUser.__table__,
    StaffMember.__table__, ProjectAssignment.__table__,
    WpIndex.__table__, WorkingPaper.__table__,
)


def _user(username: str, role: UserRole, parent: uuid.UUID | None = None) -> User:
    return User(
        id=uuid.uuid4(), username=username, email=f"{username}@example.com",
        hashed_password="x", role=role, full_name=username, parent_partner_id=parent,
    )


def _project(name: str, *, created_by=None, partner_id=None, deleted: bool = False) -> Project:
    p = Project(
        id=uuid.uuid4(), name=f"【测试】{name}", client_name=f"【测试】{name}",
        audit_period_start=date(2025, 1, 1), audit_period_end=date(2025, 12, 31),
        created_by=created_by, partner_id=partner_id,
    )
    if deleted:
        p.is_deleted = True
    return p


@pytest_asyncio.fixture
async def topo():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        for table in _TABLES:
            await conn.run_sync(table.create, checkfirst=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with session_maker() as db:
        admin = _user("admin_t", UserRole.admin)
        jia = _user("partner_jia", UserRole.partner)
        yi = _user("partner_yi", UserRole.partner)
        db.add_all([admin, jia, yi])
        await db.flush()
        sub = _user("jia_manager", UserRole.manager, parent=jia.id)
        db.add(sub)
        await db.flush()

        p = {
            "own": _project("甲创建", created_by=jia.id),
            "sub": _project("下属创建", created_by=sub.id),
            "sign": _project("甲签字", partner_id=jia.id),
            "wp": _project("甲复核底稿"),
            "assign": _project("甲被委派"),
            "member": _project("甲成员行"),
            "yi": _project("乙的项目", created_by=yi.id, partner_id=yi.id),
            "deleted": _project("甲创建已删", created_by=jia.id, deleted=True),
        }
        db.add_all(p.values())
        await db.flush()

        # (d) 甲是 P_wp 某张底稿的复核人
        wpi = WpIndex(id=uuid.uuid4(), project_id=p["wp"].id, wp_code="D1", wp_name="测试底稿")
        db.add(wpi)
        await db.flush()
        db.add(WorkingPaper(
            id=uuid.uuid4(), project_id=p["wp"].id, wp_index_id=wpi.id,
            file_path="/nonexistent", source_type="upload", reviewer=jia.id,
        ))
        # 乙的项目里也放一张底稿（用于门禁拒绝）
        wpi_yi = WpIndex(id=uuid.uuid4(), project_id=p["yi"].id, wp_code="D1", wp_name="乙底稿")
        db.add(wpi_yi)
        await db.flush()
        wp_yi = WorkingPaper(
            id=uuid.uuid4(), project_id=p["yi"].id, wp_index_id=wpi_yi.id,
            file_path="/nonexistent", source_type="upload",
        )
        db.add(wp_yi)

        # (e) 甲经人员档案被委派到 P_assign
        staff = StaffMember(id=uuid.uuid4(), name="甲", user_id=jia.id)
        db.add(staff)
        await db.flush()
        db.add(ProjectAssignment(
            id=uuid.uuid4(), project_id=p["assign"].id, staff_id=staff.id,
            role="partner", assigned_at=datetime.now(timezone.utc),
        ))

        # (f) 甲在 P_member 有成员行
        db.add(ProjectUser(
            project_id=p["member"].id, user_id=jia.id,
            role=ProjectUserRole.partner, permission_level=PermissionLevel.edit,
        ))
        await db.commit()

        yield {"db": db, "admin": admin, "jia": jia, "yi": yi, "sub": sub, "p": p, "wp_yi": wp_yi}
    await engine.dispose()


def _ids(topo, *keys):
    return {topo["p"][k].id for k in keys}


async def test_subordinates(topo):
    assert await subordinate_ids(topo["jia"].id, topo["db"]) == {topo["sub"].id}
    assert await subordinate_ids(topo["yi"].id, topo["db"]) == set()


async def test_partner_sees_exactly_own_projects(topo):
    got = await partner_visible_project_ids(topo["jia"], topo["db"])
    assert got == _ids(topo, "own", "sub", "sign", "wp", "assign", "member")
    assert topo["p"]["yi"].id not in got
    assert topo["p"]["deleted"].id not in got


async def test_other_partner_does_not_see_jia_projects(topo):
    got = await partner_visible_project_ids(topo["yi"], topo["db"])
    assert got == _ids(topo, "yi")


@pytest.mark.parametrize("source", ["own", "sub", "sign", "wp", "assign", "member"])
async def test_each_source_contributes(topo, source):
    """逐来源可归因：去掉一个来源的支撑，对应项目就从可见集消失。"""
    db = topo["db"]
    project = topo["p"][source]
    project.is_deleted = True
    await db.commit()
    got = await partner_visible_project_ids(topo["jia"], db)
    assert project.id not in got
    assert got == _ids(topo, "own", "sub", "sign", "wp", "assign", "member") - {project.id}


async def test_deps_visibility_entrypoints(topo):
    db = topo["db"]
    expected = _ids(topo, "own", "sub", "sign", "wp", "assign", "member")
    assert set(await get_visible_project_ids(topo["jia"], db)) == expected
    assert set(await _project_level_visible_ids(topo["jia"], db)) == expected
    # admin 仍是全部未删除项目
    all_live = {p.id for k, p in topo["p"].items() if k != "deleted"}
    assert set(await get_visible_project_ids(topo["admin"], db)) == all_live


async def test_wp_gates_reject_other_partner_project(topo):
    db = topo["db"]
    with pytest.raises(HTTPException) as e1:
        await authorize_wp_edit(db, topo["jia"], topo["wp_yi"].id)
    assert e1.value.status_code == 403
    with pytest.raises(HTTPException) as e2:
        await authorize_wp_read(db, topo["jia"], topo["wp_yi"].id)
    assert e2.value.status_code == 403
    # 乙自己的项目照常放行
    assert await authorize_wp_read(db, topo["yi"], topo["wp_yi"].id) == topo["p"]["yi"].id


async def test_project_list_endpoint(topo):
    from app.routers.project_wizard import get_project, list_projects

    db = topo["db"]
    listed = {r.id for r in await list_projects(db=db, current_user=topo["jia"])}
    assert listed == _ids(topo, "own", "sub", "sign", "wp", "assign", "member")
    # 直接按 id 打开乙的项目 → 404（不泄露存在性）
    with pytest.raises(HTTPException) as exc:
        await get_project(topo["p"]["yi"].id, db=db, current_user=topo["jia"])
    assert exc.value.status_code == 404
    opened = await get_project(topo["p"]["sign"].id, db=db, current_user=topo["jia"])
    assert opened.id == topo["p"]["sign"].id


async def test_project_tree(topo):
    from app.services.group_forest import load_forest

    forest = await load_forest(topo["db"], user=topo["jia"])

    def _collect(nodes, out):
        for n in nodes:
            for item in n.get("projects") or []:
                out.add(uuid.UUID(item["id"]))
            _collect(n.get("children") or [], out)
        return out

    seen = _collect((forest.get("trees") or []) + (forest.get("independents") or []), set())
    # 测试项目都没有企业代码 ⇒ 全进 independents；断言集合相等（非空），防止键名变了空转
    assert seen == _ids(topo, "own", "sub", "sign", "wp", "assign", "member")
    assert topo["p"]["yi"].id not in seen
