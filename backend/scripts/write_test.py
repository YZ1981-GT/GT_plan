"""Helper to write test file to disk"""
import os, textwrap

content = textwrap.dedent('''\
    """Phase 9 Task 1 tests"""
    from __future__ import annotations
    import uuid
    from datetime import date
    from decimal import Decimal
    import pytest
    import pytest_asyncio
    import sqlalchemy as sa
    from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.models.base import Base
    SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
    _engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    import app.models.core  # noqa: F401
    import app.models.audit_platform_models  # noqa: F401
    import app.models.report_models  # noqa: F401
    import app.models.workpaper_models  # noqa: F401
    import app.models.consolidation_models  # noqa: F401
    import app.models.staff_models  # noqa: F401
    import app.models.collaboration_models  # noqa: F401
    import app.models.ai_models  # noqa: F401
    import app.models.extension_models  # noqa: F401
    import app.models.gt_coding_models  # noqa: F401
    import app.models.t_account_models  # noqa: F401
    import app.models.attachment_models  # noqa: F401
    from app.models.staff_models import ProjectAssignment, StaffMember, WorkHour
    from app.models.core import Project

    # Stub for workpapers table (referenced by AI models FK)
    class _WPStub(Base):
        __tablename__ = "workpapers"
        __table_args__ = {"extend_existing": True}
        id = sa.Column(sa.Uuid, primary_key=True)

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
        s = StaffMember(name="Test", employee_no="T-001")
        db_session.add(s)
        await db_session.flush()
        assert s.id is not None

    @pytest.mark.asyncio
    async def test_staff_service_crud(db_session):
        from app.services.staff_service import StaffService
        svc = StaffService(db_session)
        staff = await svc.create_staff({"name": "Test", "employee_no": "T-002"})
        items, total = await svc.list_staff()
        assert total == 1

    @pytest.mark.asyncio
    async def test_assignment_service(db_session):
        from app.services.assignment_service import AssignmentService
        svc = AssignmentService(db_session)
        s = StaffMember(name="Assign", employee_no="A-001")
        db_session.add(s)
        p = Project(name="Proj", client_name="Client")
        db_session.add(p)
        await db_session.flush()
        await svc.save_assignments(p.id, [{"staff_id": s.id, "role": "auditor", "assigned_cycles": ["B"]}])
        result = await svc.list_assignments(p.id)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_workhour_service(db_session):
        from app.services.workhour_service import WorkHourService
        svc = WorkHourService(db_session)
        s = StaffMember(name="WH", employee_no="W-001")
        db_session.add(s)
        p = Project(name="WH Proj", client_name="Client")
        db_session.add(p)
        await db_session.flush()
        wh, _ = await svc.create_hour(s.id, {"project_id": p.id, "work_date": date(2026, 4, 16), "hours": Decimal("8")})
        assert wh.hours == Decimal("8")

    @pytest.mark.asyncio
    async def test_workhour_over_24h(db_session):
        from app.services.workhour_service import WorkHourService
        svc = WorkHourService(db_session)
        s = StaffMember(name="OT", employee_no="W-002")
        db_session.add(s)
        p1 = Project(name="A", client_name="A")
        p2 = Project(name="B", client_name="B")
        db_session.add_all([p1, p2])
        await db_session.flush()
        await svc.create_hour(s.id, {"project_id": p1.id, "work_date": date(2026, 4, 16), "hours": Decimal("16")})
        _, warnings = await svc.create_hour(s.id, {"project_id": p2.id, "work_date": date(2026, 4, 16), "hours": Decimal("10")})
        assert any(w["warning_type"] == "daily_over_24h" for w in warnings)
''')

target = os.path.join(os.path.dirname(__file__), '..', 'tests', 'test_staff_service.py')
with open(target, 'w', encoding='utf-8') as f:
    f.write(content)
print(f"Written {len(content)} chars")
