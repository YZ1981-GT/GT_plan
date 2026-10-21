"""eqcr_resolver 冒烟验证（partner-manager-edit-permission 任务 2.6；需求 7.1、7.6、11.1）。

完整的模型对拍性质测试与固定样例 ①~⑩ 在 ``test_eqcr_resolver_property.py``（任务 2.7）。本文件只钉住：
- ``is_project_eqcr`` 对五种情形的结论：真实 SQLite 库，不替换任何判定；
- ``project_eqcr_user_ids`` 只按委派条件取人：排除只有全局角色为 eqcr、委派或人员库记录已删除、
  只在他项目有委派的用户，以及未关联用户的人员库记录；
- 不经缓存：同一会话内改动删除标记后，下一次判定即按改动后的数据得出结论；
- 出错语义：故障注在下一层（委派查询、``db.execute``），异常原样冒泡，不按「非 EQCR」返回。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base, UserRole
from app.models.core import Project, User
from app.models.staff_models import ProjectAssignment, StaffMember
from app.services import eqcr_resolver
from app.services.eqcr_resolver import is_project_eqcr, project_eqcr_user_ids

_TABLES = [User.__table__, Project.__table__, StaffMember.__table__, ProjectAssignment.__table__]


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_TABLES)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


@dataclass
class _World:
    p: uuid.UUID
    q: uuid.UUID
    global_eqcr: User  # 全局角色 eqcr，无任何委派
    alias: User  # 全局 auditor，P 上委派「独立复核合伙人」
    alias_assignment: ProjectAssignment
    deleted_assignment: User  # 全局 auditor，P 上的 eqcr 委派已删除
    deleted_staff: User  # 全局 auditor，P 上 eqcr 委派的人员库记录已删除
    deleted_staff_record: StaffMember
    other_project: User  # 全局 auditor，只在 Q 上有 eqcr 委派


async def _add(db: AsyncSession, row):
    db.add(row)
    await db.flush()
    return row


async def _user(db: AsyncSession, role: UserRole) -> User:
    tag = uuid.uuid4().hex[:12]
    return await _add(db, User(username=f"u-{tag}", email=f"{tag}@test.local", hashed_password="x", role=role))


async def _staff(db: AsyncSession, user: User | None, *, deleted: bool = False) -> StaffMember:
    return await _add(db, StaffMember(user_id=user.id if user else None, name="测试人员", is_deleted=deleted))


async def _assign(db: AsyncSession, project_id: uuid.UUID, staff: StaffMember, role: str,
                  *, deleted: bool = False) -> ProjectAssignment:
    return await _add(db, ProjectAssignment(project_id=project_id, staff_id=staff.id, role=role, is_deleted=deleted))


@pytest_asyncio.fixture
async def world(db: AsyncSession) -> _World:
    p = (await _add(db, Project(name="【测试】P", client_name="甲"))).id
    q = (await _add(db, Project(name="【测试】Q", client_name="乙"))).id

    global_eqcr = await _user(db, UserRole.eqcr)
    await _staff(db, global_eqcr)

    alias = await _user(db, UserRole.auditor)
    alias_assignment = await _assign(db, p, await _staff(db, alias), "独立复核合伙人")

    deleted_assignment = await _user(db, UserRole.auditor)
    await _assign(db, p, await _staff(db, deleted_assignment), "eqcr", deleted=True)

    deleted_staff = await _user(db, UserRole.auditor)
    deleted_staff_record = await _staff(db, deleted_staff, deleted=True)
    await _assign(db, p, deleted_staff_record, "eqcr")

    other_project = await _user(db, UserRole.auditor)
    await _assign(db, q, await _staff(db, other_project), "eqcr")

    await _assign(db, p, await _staff(db, None), "eqcr")  # 干扰：未关联用户的人员库记录

    return _World(p, q, global_eqcr, alias, alias_assignment, deleted_assignment, deleted_staff,
                  deleted_staff_record, other_project)


async def test_is_project_eqcr_five_cases(db: AsyncSession, world: _World):
    assert await is_project_eqcr(db, world.global_eqcr, world.p) is True
    assert await is_project_eqcr(db, world.alias, world.p) is True
    assert await is_project_eqcr(db, world.deleted_assignment, world.p) is False
    assert await is_project_eqcr(db, world.deleted_staff, world.p) is False
    assert await is_project_eqcr(db, world.other_project, world.p) is False
    # 对照：同一条委派在它所在的项目计入 ⇒ 上一条的否来自「只看本项目」
    assert await is_project_eqcr(db, world.other_project, world.q) is True


async def test_project_eqcr_user_ids_assignment_condition_only(db: AsyncSession, world: _World):
    assert await project_eqcr_user_ids(db, world.p) == {world.alias.id}
    assert await project_eqcr_user_ids(db, world.q) == {world.other_project.id}


async def test_no_cache_follows_current_rows(db: AsyncSession, world: _World):
    assert await is_project_eqcr(db, world.alias, world.p) is True
    world.alias_assignment.is_deleted = True
    await db.flush()
    assert await is_project_eqcr(db, world.alias, world.p) is False

    assert await is_project_eqcr(db, world.deleted_staff, world.p) is False
    world.deleted_staff_record.is_deleted = False
    await db.flush()
    assert await is_project_eqcr(db, world.deleted_staff, world.p) is True


async def test_fault_in_assignment_query_propagates(db: AsyncSession, world: _World, monkeypatch):
    boom = RuntimeError("委派查询失败（注入）")

    async def _raise(*_args, **_kwargs):
        raise boom

    monkeypatch.setattr(eqcr_resolver, "_count_project_eqcr_assignments", _raise)
    with pytest.raises(RuntimeError) as exc_info:
        await is_project_eqcr(db, world.alias, world.p)
    assert exc_info.value is boom


async def test_fault_in_db_execute_propagates(db: AsyncSession, world: _World, monkeypatch):
    boom = ConnectionError("数据库连接中断（注入）")

    async def _raise(*_args, **_kwargs):
        raise boom

    monkeypatch.setattr(db, "execute", _raise)
    with pytest.raises(ConnectionError) as count_exc:
        await is_project_eqcr(db, world.alias, world.p)
    assert count_exc.value is boom
    with pytest.raises(ConnectionError) as ids_exc:
        await project_eqcr_user_ids(db, world.p)
    assert ids_exc.value is boom
