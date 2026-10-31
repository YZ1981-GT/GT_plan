"""P2.3: wp-index 只读负责人 JOIN 与回退契约。"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User, UserRole
from app.models.staff_models import StaffMember
from app.models.workpaper_models import WpFileStatus, WpIndex, WpSourceType, WpStatus, WorkingPaper

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON


@pytest_asyncio.fixture
async def assignee_db() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    tables = [
        User.__table__,
        Project.__table__,
        StaffMember.__table__,
        WpIndex.__table__,
        WorkingPaper.__table__,
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_wp_index_resolves_staff_name_username_fallback_and_empty(
    assignee_db: AsyncSession,
):
    project_id = uuid.uuid4()
    staff_user = User(
        id=uuid.uuid4(),
        username="staff-login",
        email="staff-login@test.local",
        hashed_password="not-loginable",
        role=UserRole.auditor,
    )
    fallback_user = User(
        id=uuid.uuid4(),
        username="fallback-login",
        email="fallback-login@test.local",
        hashed_password="not-loginable",
        role=UserRole.auditor,
    )
    project = Project(
        id=project_id,
        name="P2.3 测试项目",
        client_name="测试客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
    )
    idx_staff = WpIndex(
        project_id=project_id,
        wp_code="S32-1",
        wp_name="有人员库姓名",
        audit_cycle="S",
        assigned_to=staff_user.id,
        status=WpStatus.not_started,
    )
    idx_fallback = WpIndex(
        project_id=project_id,
        wp_code="S33-1",
        wp_name="无人员库记录",
        audit_cycle="S",
        assigned_to=fallback_user.id,
        status=WpStatus.not_started,
    )
    idx_empty = WpIndex(
        project_id=project_id,
        wp_code="S34-1",
        wp_name="未分配负责人",
        audit_cycle="S",
        status=WpStatus.not_started,
    )
    assignee_db.add_all([
        project,
        staff_user,
        fallback_user,
        StaffMember(user_id=staff_user.id, name="张三"),
        idx_staff,
        idx_fallback,
        idx_empty,
    ])
    await assignee_db.flush()
    assignee_db.add(WorkingPaper(
        project_id=project_id,
        wp_index_id=idx_staff.id,
        file_path="p2-3/S32-1.xlsx",
        source_type=WpSourceType.template,
        status=WpFileStatus.draft,
    ))
    await assignee_db.flush()

    from app.routers.wp_relation_router import list_wp_index

    rows = await list_wp_index(project_id, assignee_db, current_user=staff_user)
    by_code = {row["wp_code"]: row for row in rows}

    assert by_code["S32-1"]["assigned_to_name"] == "张三"
    assert by_code["S32-1"]["assigned_to_username"] == "staff-login"
    assert by_code["S33-1"]["assigned_to_name"] == "fallback-login"
    assert by_code["S33-1"]["assigned_to_username"] == "fallback-login"
    assert by_code["S34-1"]["assigned_to"] is None
    assert by_code["S34-1"]["assigned_to_name"] is None
    assert by_code["S34-1"]["assigned_to_username"] is None
