"""Phase 9 Task 1 tests"""
from __future__ import annotations
import uuid
from datetime import date, datetime
from decimal import Decimal
import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.models.base import Base
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
import app.models.core  # noqa
import app.models.audit_platform_models  # noqa
import app.models.report_models  # noqa
import app.models.workpaper_models  # noqa
import app.models.consolidation_models  # noqa
import app.models.staff_models  # noqa
import app.models.collaboration_models  # noqa
import app.models.ai_models  # noqa
import app.models.extension_models  # noqa
import app.models.gt_coding_models  # noqa
import app.models.t_account_models  # noqa
import app.models.attachment_models  # noqa
from app.models.staff_models import ProjectAssignment, StaffMember, WorkHour
from app.models.core import Project

@pytest_asyncio.fixture
async def db_session():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()

@pytest.mark.asyncio
async def test_staff_create(db_session):
    s = StaffMember(name="张三", employee_no="SJ2-001", department="审计二部")
    db_session.add(s)
    await db_session.flush()
    assert s.id is not None
    assert s.is_deleted is False



@pytest.mark.asyncio
async def test_assignment_create(db_session):
    s = StaffMember(name="王五", employee_no="SJ2-002")
    db_session.add(s)
    p = Project(name="测试项目", client_name="客户")
    db_session.add(p)
    await db_session.flush()
    pa = ProjectAssignment(project_id=p.id, staff_id=s.id, role="auditor", assigned_cycles=["B"])
    db_session.add(pa)
    await db_session.flush()
    assert pa.id is not None

@pytest.mark.asyncio
async def test_workhour_create(db_session):
    s = StaffMember(name="赵六", employee_no="SJ2-003")
    db_session.add(s)
    p = Project(name="工时项目", client_name="客户")
    db_session.add(p)
    await db_session.flush()
    wh = WorkHour(staff_id=s.id, project_id=p.id, work_date=date(2026, 4, 16), hours=Decimal("8.0"))
    db_session.add(wh)
    await db_session.flush()
    assert wh.status == "draft"

@pytest.mark.asyncio
async def test_staff_service_crud(db_session):
    from app.services.staff_service import StaffService
    svc = StaffService(db_session)
    staff = await svc.create_staff({"name": "测试", "employee_no": "T-001"})
    assert staff.name == "测试"
    items, total = await svc.list_staff()
    assert total == 1
    updated = await svc.update_staff(staff.id, {"name": "新名"})
    assert updated.name == "新名"

@pytest.mark.asyncio
async def test_staff_search(db_session):
    from app.services.staff_service import StaffService
    svc = StaffService(db_session)
    await svc.create_staff({"name": "张三", "employee_no": "S-001"})
    await svc.create_staff({"name": "李四", "employee_no": "S-002"})
    items, total = await svc.list_staff(search="张")
    assert total == 1

@pytest.mark.asyncio
async def test_assignment_service(db_session):
    from app.services.assignment_service import AssignmentService
    svc = AssignmentService(db_session)
    s = StaffMember(name="委派", employee_no="A-001")
    db_session.add(s)
    p = Project(name="委派项目", client_name="客户")
    db_session.add(p)
    await db_session.flush()
    await svc.save_assignments(p.id, [{"staff_id": s.id, "role": "auditor", "assigned_cycles": ["B"]}])
    result = await svc.list_assignments(p.id)
    assert len(result) == 1

@pytest.mark.asyncio
async def test_workhour_service(db_session):
    from app.services.workhour_service import WorkHourService
    svc = WorkHourService(db_session)
    s = StaffMember(name="工时", employee_no="W-001")
    db_session.add(s)
    p = Project(name="工时项目", client_name="客户")
    db_session.add(p)
    await db_session.flush()
    wh, _ = await svc.create_hour(s.id, {"project_id": p.id, "work_date": date(2026, 4, 16), "hours": Decimal("8")})
    assert wh.hours == Decimal("8")
    hours = await svc.list_hours(s.id)
    assert len(hours) == 1

@pytest.mark.asyncio
async def test_workhour_over_24h(db_session):
    from app.services.workhour_service import WorkHourService
    svc = WorkHourService(db_session)
    s = StaffMember(name="超时", employee_no="W-002")
    db_session.add(s)
    p1 = Project(name="A", client_name="A")
    p2 = Project(name="B", client_name="B")
    db_session.add_all([p1, p2])
    await db_session.flush()
    await svc.create_hour(s.id, {"project_id": p1.id, "work_date": date(2026, 4, 16), "hours": Decimal("16")})
    _, warnings = await svc.create_hour(s.id, {"project_id": p2.id, "work_date": date(2026, 4, 16), "hours": Decimal("10")})
    assert any(w["warning_type"] == "daily_over_24h" for w in warnings)

@pytest.mark.asyncio
async def test_workhour_summary(db_session):
    from app.services.workhour_service import WorkHourService
    svc = WorkHourService(db_session)
    s = StaffMember(name="汇总", employee_no="W-003")
    db_session.add(s)
    p = Project(name="汇总项目", client_name="客户")
    db_session.add(p)
    await db_session.flush()
    await svc.create_hour(s.id, {"project_id": p.id, "work_date": date(2026, 4, 15), "hours": Decimal("8")})
    await svc.create_hour(s.id, {"project_id": p.id, "work_date": date(2026, 4, 16), "hours": Decimal("6")})
    summary = await svc.project_summary(p.id)
    assert len(summary) == 1
    assert summary[0]["total_hours"] == 14.0
