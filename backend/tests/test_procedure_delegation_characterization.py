"""Wave 1 baseline characterization for procedure delegation.

These tests intentionally exercise the current ORM and router/service code. They
must not import or emulate the future V105 row-task domain model.
"""
from __future__ import annotations

import copy
import uuid
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base, ProjectStatus, ProjectType, UserRole
from app.models.core import Project, User
from app.models.phase15_models import TaskEvent
from app.models.procedure_models import ProcedureInstance
from app.models.workpaper_models import (
    WorkingPaper,
    WpCrossRef,
    WpFileStatus,
    WpIndex,
    WpReviewStatus,
    WpSourceType,
    WpStatus,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if hasattr(SQLiteTypeCompiler, "visit_uuid"):
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

_CURRENT_TABLES = [
    User.__table__,
    Project.__table__,
    WpIndex.__table__,
    WorkingPaper.__table__,
    WpCrossRef.__table__,
    ProcedureInstance.__table__,
    TaskEvent.__table__,
]
_FUTURE_V105_TABLES = {
    "procedure_row_definitions",
    "procedure_row_tasks",
    "procedure_row_task_history",
    "procedure_operation_previews",
}


@pytest_asyncio.fixture
async def characterized_db() -> dict[str, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_CURRENT_TABLES)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        user = User(
            id=uuid.uuid4(), username="wave1_manager", email="wave1@test.invalid",
            hashed_password="not-used", role=UserRole.manager,
        )
        project_a = Project(
            id=uuid.uuid4(), name="Wave1-A_2025", client_name="Client A",
            project_type=ProjectType.annual, status=ProjectStatus.planning,
            audit_year=2025, business_category="C",
        )
        project_b = Project(
            id=uuid.uuid4(), name="Wave1-B_2025", client_name="Client B",
            project_type=ProjectType.annual, status=ProjectStatus.planning,
            audit_year=2025, business_category="C",
        )
        index = WpIndex(
            id=uuid.uuid4(), project_id=project_a.id, wp_code="D1",
            wp_name="应收票据", audit_cycle="D", status=WpStatus.not_started,
        )
        wp = WorkingPaper(
            id=uuid.uuid4(), project_id=project_a.id, wp_index_id=index.id,
            file_path="tests/fixtures/nonexistent-D1.xlsx",
            source_type=WpSourceType.template, status=WpFileStatus.draft,
            review_status=WpReviewStatus.not_submitted, file_version=7,
            parsed_data={"html_data": {"程序表D1A": {"seed": "unchanged"}}},
        )
        procedures = [
            ProcedureInstance(
                id=uuid.uuid4(), project_id=project_a.id, audit_cycle="D",
                procedure_code="D1", procedure_name="应收票据", wp_code="D1",
                wp_id=wp.id, sort_order=10,
            ),
            ProcedureInstance(
                id=uuid.uuid4(), project_id=project_a.id, audit_cycle="D",
                procedure_code="D2", procedure_name="应收账款", wp_code="D2",
                sort_order=20,
            ),
            ProcedureInstance(
                id=uuid.uuid4(), project_id=project_b.id, audit_cycle="D",
                procedure_code="D1", procedure_name="应收票据", wp_code="D1",
                sort_order=10,
            ),
        ]
        event = TaskEvent(
            id=uuid.uuid4(), project_id=project_a.id, event_type="trim_applied",
            payload={"baseline": True}, status="queued", trace_id="wave1-baseline",
        )
        db.add_all([user, project_a, project_b, index, wp, *procedures, event])
        await db.commit()
        yield {
            "db": db, "engine": engine, "user": user, "wp": wp,
            "project_a": project_a, "project_b": project_b,
        }
    await engine.dispose()


def _stable(value):
    if isinstance(value, (uuid.UUID, date, datetime)):
        return str(value)
    return copy.deepcopy(value)


async def _domain_snapshot(db: AsyncSession, wp_id: uuid.UUID) -> dict:
    wp = (await db.execute(
        sa.select(WorkingPaper).where(WorkingPaper.id == wp_id)
    )).scalar_one()
    procedures = (await db.execute(
        sa.select(ProcedureInstance).order_by(ProcedureInstance.id)
    )).scalars().all()
    events = (await db.execute(
        sa.select(TaskEvent).order_by(TaskEvent.id)
    )).scalars().all()

    def rows(items):
        return [
            {column.name: _stable(getattr(item, column.name)) for column in item.__table__.columns}
            for item in items
        ]

    return {
        "working_paper": {
            "parsed_data": copy.deepcopy(wp.parsed_data),
            "file_version": wp.file_version,
        },
        "procedure_instances": rows(procedures),
        "task_events": rows(events),
    }


@pytest.mark.asyncio
async def test_procedure_instance_is_stable_project_wp_scope(characterized_db):
    """Current ProcedureInstance is a workpaper scope, not a procedure row."""
    from app.routers.procedures import get_procedures

    db = characterized_db["db"]
    project_a = characterized_db["project_a"]
    project_b = characterized_db["project_b"]
    user = characterized_db["user"]

    first = await get_procedures(project_a.id, "D", db=db, user=user)
    second = await get_procedures(project_a.id, "D", db=db, user=user)
    isolated = await get_procedures(project_b.id, "D", db=db, user=user)

    first_identity = {(row["wp_code"], row["id"]) for row in first}
    current_columns = set(ProcedureInstance.__table__.columns.keys())
    assert "wp_code" in current_columns
    assert {"row_key", "sheet_key", "definition_key"}.isdisjoint(current_columns)
    assert first_identity == {(row["wp_code"], row["id"]) for row in second}
    assert len({row["wp_code"] for row in first}) == len(first) == 2
    assert {row["wp_code"] for row in first} == {"D1", "D2"}
    assert len(isolated) == 1 and isolated[0]["wp_code"] == "D1"
    assert isolated[0]["id"] not in {row["id"] for row in first}
    assert all(row["procedure_code"] == row["wp_code"] for row in first + isolated)


@pytest.mark.asyncio
async def test_existing_gets_leave_workpaper_procedures_and_events_unchanged(
    characterized_db, monkeypatch,
):
    """Both existing GET call paths are observationally read-only."""
    from app.routers.procedures import get_procedures
    from app.routers import wp_render_config as render_module

    db = characterized_db["db"]
    project = characterized_db["project_a"]
    wp = characterized_db["wp"]
    wp_id = wp.id
    user = characterized_db["user"]

    before_procedures = await _domain_snapshot(db, wp_id)
    result = await get_procedures(project.id, "D", db=db, user=user)
    assert result
    assert await _domain_snapshot(db, wp_id) == before_procedures

    classification_service = MagicMock()
    classification_service.get_classification = AsyncMock(return_value=[])
    version_service = MagicMock()
    version_service.get_current_version = AsyncMock(
        return_value=MagicMock(version="baseline", id=uuid.uuid4())
    )
    monkeypatch.setattr(
        render_module, "WpClassificationService", lambda _db: classification_service
    )
    monkeypatch.setattr(
        render_module, "WpTemplateVersionService", lambda _db: version_service
    )
    monkeypatch.setattr(
        render_module, "_maybe_custom_classifications", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        render_module, "resolve_package_sheets", AsyncMock(return_value=None)
    )

    before_render = await _domain_snapshot(db, wp_id)
    rendered = await render_module.get_render_config(
        wp_id=wp_id, sheet_name=None, component_type=None,
        db=db, current_user=user,
    )
    assert rendered["wp_id"] == str(wp_id)
    assert rendered["wp_code"] == "D1"
    assert rendered["sheets"] == []
    assert await _domain_snapshot(db, wp_id) == before_render


@pytest.mark.asyncio
async def test_v105_tables_registered_in_orm_but_absent_from_legacy_characterization_db(
    characterized_db,
):
    """Task 2 后：4 张 V105 表已登记 ORM；特征库仍仅建 legacy 子集（pre-Task-2 拓扑）。"""
    engine = characterized_db["engine"]
    async with engine.connect() as conn:
        table_names = set(await conn.run_sync(lambda sync: sa.inspect(sync).get_table_names()))

    # 特征库 create_all(tables=_CURRENT_TABLES) 只建 legacy 子集，V105 表不在该内存库。
    assert _FUTURE_V105_TABLES.isdisjoint(table_names)
    # Task 2 落地：4 张 V105 表已登记到 ORM Base.metadata。
    assert _FUTURE_V105_TABLES <= set(Base.metadata.tables)
    assert {"procedure_instances", "working_paper", "task_events"} <= table_names
