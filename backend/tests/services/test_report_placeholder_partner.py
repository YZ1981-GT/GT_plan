"""报告正文签字合伙人兜底取数（spec deliverable-trio-generation-accuracy §3，ReportPlaceholderService）。

真库现状（2026-10-16）：项目委派界面的角色取值是 ``signing_partner``，旧 SQL 只认 ``partner`` ⇒ 界面委派的签字合伙人
永远取不到；姓名取 ``COALESCE(partner_name, name)``，而 ``staff_members.partner_name`` 是该员工**所属合伙人**的名字。
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import MetaData
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.core import Project
from app.models.staff_models import ProjectAssignment, StaffMember

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

from app.services.report_placeholder_service import ReportPlaceholderService  # noqa: E402

_TABLES = [Project.__table__, StaffMember.__table__, ProjectAssignment.__table__]


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: MetaData().create_all(c, tables=_TABLES))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _project_with(db: AsyncSession, *assignments: tuple[str, str, bool]) -> Project:
    project = Project(id=uuid.uuid4(), name="测试_2025", client_name="测试有限公司", report_scope="standalone")
    db.add(project)
    for name, role, deleted in assignments:
        staff = StaffMember(id=uuid.uuid4(), name=name, partner_name="所属合伙人李四")
        db.add(staff)
        db.add(ProjectAssignment(id=uuid.uuid4(), project_id=project.id, staff_id=staff.id, role=role,
                                 is_deleted=deleted))
    await db.flush()
    return project


@pytest.mark.asyncio
async def test_signing_partner_role_and_own_name(db):
    project = await _project_with(db, ("项目经理王五", "manager", False), ("签字合伙人张三", "signing_partner", False))
    # 取本人姓名，不是 partner_name 里记的「所属合伙人」；manager 角色不算
    assert await ReportPlaceholderService(db)._resolve_partner_name(project) == "签字合伙人张三"


@pytest.mark.asyncio
async def test_signing_partner_preferred_over_legacy_partner_role(db):
    project = await _project_with(db, ("历史合伙人赵六", "partner", False), ("签字合伙人张三", "signing_partner", False))
    assert await ReportPlaceholderService(db)._resolve_partner_name(project) == "签字合伙人张三"


@pytest.mark.asyncio
async def test_deleted_assignment_ignored(db):
    project = await _project_with(db, ("已移出的合伙人", "signing_partner", True))
    assert await ReportPlaceholderService(db)._resolve_partner_name(project) is None
