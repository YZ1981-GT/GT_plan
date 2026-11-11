"""部门负责人项目可见性（dept_head_visibility_service + deps 门禁兜底）。

需求：部门负责人（``sys_dept.head_id``）能看见本部门（含子部门）成员参与的全部项目，
并能只读打开这些项目（即便不是成员行）。

拓扑：
  部门 D1（负责人 = 合伙人甲），子部门 D1a（负责人 = 合伙人丙）。
  用户：甲(D1 负责人, dept=D1) / 李(auditor, dept=D1) / 王(auditor, dept=D1a) / 外人(dept=None)。
  项目：
    P_li     —— 李创建（D1 成员）          → 甲可见、可只读打开
    P_wang   —— 王创建（D1a 成员，子部门）  → 甲可见（递归子部门）
    P_outside—— 外人创建（无部门）          → 甲不可见
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.deps import assert_project_permission, get_visible_project_ids
from app.models.base import UserRole
from app.models.core import Department, Project, ProjectUser, User
from app.models.staff_models import ProjectAssignment, StaffMember
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.dept_head_visibility_service import (
    dept_head_visible_project_ids,
    headed_department_ids,
)

pytestmark = pytest.mark.asyncio

_TABLES = (
    User.__table__, Project.__table__, ProjectUser.__table__, Department.__table__,
    StaffMember.__table__, ProjectAssignment.__table__,
    WpIndex.__table__, WorkingPaper.__table__,
)


def _user(username: str, role: UserRole, dept_id=None) -> User:
    return User(
        id=uuid.uuid4(), username=username, email=f"{username}@example.com",
        hashed_password="x", role=role, full_name=username, dept_id=dept_id,
    )


def _project(name: str, *, created_by=None) -> Project:
    return Project(
        id=uuid.uuid4(), name=f"【测试】{name}", client_name=f"【测试】{name}",
        audit_period_start=date(2025, 1, 1), audit_period_end=date(2025, 12, 31),
        created_by=created_by,
    )


@pytest_asyncio.fixture
async def topo():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        for table in _TABLES:
            await conn.run_sync(table.create, checkfirst=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with session_maker() as db:
        jia = _user("partner_jia", UserRole.partner)
        bing = _user("partner_bing", UserRole.partner)
        db.add_all([jia, bing])
        await db.flush()

        d1 = Department(id=uuid.uuid4(), name="审计一部", head_id=jia.id)
        db.add(d1)
        await db.flush()
        d1a = Department(id=uuid.uuid4(), name="审计一部一组", head_id=bing.id, parent_id=d1.id)
        db.add(d1a)
        await db.flush()

        li = _user("auditor_li", UserRole.auditor, dept_id=d1.id)
        wang = _user("auditor_wang", UserRole.auditor, dept_id=d1a.id)
        outsider = _user("auditor_out", UserRole.auditor, dept_id=None)
        # 甲本人也归属 D1
        jia.dept_id = d1.id
        db.add_all([li, wang, outsider])
        await db.flush()

        p = {
            "li": _project("李创建", created_by=li.id),
            "wang": _project("王创建", created_by=wang.id),
            "outside": _project("外人创建", created_by=outsider.id),
        }
        db.add_all(p.values())
        await db.flush()
        await db.commit()

        yield {"db": db, "jia": jia, "bing": bing, "li": li, "wang": wang,
               "outsider": outsider, "d1": d1, "d1a": d1a, "p": p}
    await engine.dispose()


async def test_headed_departments_include_subtree(topo):
    got = await headed_department_ids(topo["jia"].id, topo["db"])
    assert got == {topo["d1"].id, topo["d1a"].id}
    # 子部门负责人只负责子部门
    got_bing = await headed_department_ids(topo["bing"].id, topo["db"])
    assert got_bing == {topo["d1a"].id}


async def test_dept_head_sees_department_and_subdept_projects(topo):
    got = await dept_head_visible_project_ids(topo["jia"], topo["db"])
    assert topo["p"]["li"].id in got       # 本部门成员创建
    assert topo["p"]["wang"].id in got     # 子部门成员创建（递归）
    assert topo["p"]["outside"].id not in got  # 无部门成员创建


async def test_non_head_gets_empty_set(topo):
    # 外人不负责任何部门 → 空集
    got = await dept_head_visible_project_ids(topo["outsider"], topo["db"])
    assert got == set()


async def test_visible_project_ids_unions_dept_head(topo):
    # 甲作为 auditor-less partner，没有任何成员行 / 签字 / 创建，可见集应仅来自部门负责人并集
    visible = set(await get_visible_project_ids(topo["jia"], topo["db"]))
    assert topo["p"]["li"].id in visible
    assert topo["p"]["wang"].id in visible
    assert topo["p"]["outside"].id not in visible


async def test_dept_head_can_open_readonly_but_not_edit(topo):
    db, jia = topo["db"], topo["jia"]
    pid = topo["p"]["li"].id
    # 只读放行
    user = await assert_project_permission(db, jia, pid, "readonly")
    assert user.id == jia.id
    # 编辑仍拒绝（仅授予只读，不越权写）
    with pytest.raises(HTTPException) as ei:
        await assert_project_permission(db, jia, pid, "edit")
    assert ei.value.status_code == 403


async def test_non_head_cannot_open_dept_project(topo):
    db = topo["db"]
    pid = topo["p"]["li"].id
    with pytest.raises(HTTPException) as ei:
        await assert_project_permission(db, topo["outsider"], pid, "readonly")
    assert ei.value.status_code == 403
