# Feature: custom-workpaper-formula-binding — 14.3 动态 wp_formula 依赖联动
"""引用方底稿在源单元格变更后应标记 prefill_stale。"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User, UserRole
from app.models.workpaper_models import (
    WorkingPaper,
    WpFileStatus,
    WpFormula,
    WpIndex,
    WpSourceType,
)
from app.services.wp_formula_linkage_service import (
    expression_references_cell,
    find_dependent_wp_ids,
    mark_working_papers_stale,
    propagate_custom_wp_cell_change,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

import app.models.core  # noqa: F401
import app.models.workpaper_models  # noqa: F401

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

PROJECT_ID = uuid.uuid4()
WP_INDEX_A = uuid.uuid4()
WP_INDEX_B = uuid.uuid4()
WP_ID_A = uuid.uuid4()
WP_ID_B = uuid.uuid4()
CODE_A = "CUST-A"
CODE_B = "CUST-B"


@pytest_asyncio.fixture
async def db_session():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        user = User(
            id=uuid.uuid4(),
            username="linkage_user",
            email="l@t.com",
            hashed_password="x",
            role=UserRole.admin,
            is_active=True,
        )
        project = Project(
            id=PROJECT_ID,
            name="联动测试",
            client_name="客户",
            project_type=ProjectType.annual,
            status=ProjectStatus.planning,
            created_by=user.id,
            audit_period_end=date(2025, 12, 31),
            template_type="soe",
        )
        session.add_all([user, project])
        await session.flush()
        for wp_id, idx_id, code in (
            (WP_ID_A, WP_INDEX_A, CODE_A),
            (WP_ID_B, WP_INDEX_B, CODE_B),
        ):
            session.add(
                WpIndex(
                    id=idx_id,
                    project_id=PROJECT_ID,
                    wp_code=code,
                    wp_name=code,
                    audit_cycle="A",
                )
            )
            session.add(
                WorkingPaper(
                    id=wp_id,
                    project_id=PROJECT_ID,
                    wp_index_id=idx_id,
                    file_path=f"/tmp/{code}.xlsx",
                    source_type=WpSourceType.manual,
                    status=WpFileStatus.draft,
                    prefill_stale=False,
                )
            )
        session.add(
            WpFormula(
                project_id=PROJECT_ID,
                wp_id=WP_ID_B,
                sheet_name="审定表",
                target_cell="C10",
                expression=f"WP('{CODE_A}','B5')+100",
            )
        )
        await session.commit()
        yield session
    await test_engine.dispose()


def test_expression_references_cell():
    assert expression_references_cell("WP('CUST-A','B5')+1", "CUST-A", "B5")
    assert not expression_references_cell("WP('CUST-A','B5')", "CUST-A", "C6")
    assert not expression_references_cell("WP('OTHER','B5')", "CUST-A", "B5")


@pytest.mark.asyncio
async def test_find_dependent_wp_ids(db_session: AsyncSession):
    deps = await find_dependent_wp_ids(db_session, PROJECT_ID, CODE_A, "B5")
    assert WP_ID_B in deps
    assert WP_ID_A not in deps


@pytest.mark.asyncio
async def test_mark_working_papers_stale(db_session: AsyncSession):
    n = await mark_working_papers_stale(PROJECT_ID, [WP_ID_B], db=db_session)
    assert n == 1
    wp = await db_session.get(WorkingPaper, WP_ID_B)
    assert wp is not None
    assert wp.prefill_stale is True


@pytest.mark.asyncio
async def test_propagate_custom_wp_cell_change_marks_dependent(db_session: AsyncSession):
    result = await propagate_custom_wp_cell_change(
        db_session,
        project_id=PROJECT_ID,
        year=2025,
        wp_code=CODE_A,
        sheet_name="审定表",
        cell_ref="B5",
    )
    assert WP_ID_B in [uuid.UUID(x) for x in result["dynamic_dependents"]]
    wp_b = await db_session.get(WorkingPaper, WP_ID_B)
    assert wp_b is not None
    assert wp_b.prefill_stale is True
