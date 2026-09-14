"""Task 23: A1 seq9 auto 建议 — a16_sign_status_check

验证 procedure_table_auto_service 的 a16_sign_status_check 数据源：
1. selected_version 存在且 sign_status=signed → step_status=completed, summary 含"已签署"
2. selected_version 存在且 sign_status=sent → step_status=in_progress, summary 含"已发出"
3. selected_version 存在且 sign_status=pending → 无 step_status, summary 含"待签署"
4. 无 selected_version → 无 step_status, summary="待确定主版本"
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.base import Base

# SQLite JSONB 兼容
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

# 注册所有模型
import app.models.core  # noqa: E402, F401
import app.models.audit_platform_models  # noqa: E402, F401
import app.models.report_models  # noqa: E402, F401
import app.models.workpaper_models  # noqa: E402, F401
import app.models.consolidation_models  # noqa: E402, F401
import app.models.staff_models  # noqa: E402, F401
import app.models.collaboration_models  # noqa: E402, F401
import app.models.ai_models  # noqa: E402, F401
import app.models.extension_models  # noqa: E402, F401
import app.models.gt_coding_models  # noqa: E402, F401
import app.models.t_account_models  # noqa: E402, F401
import app.models.attachment_models  # noqa: E402, F401
import app.models.phase13_models  # noqa: E402, F401
import app.models.eqcr_models  # noqa: E402, F401
import app.models.related_party_models  # noqa: E402, F401
import app.models.phase14_models  # noqa: E402, F401

from app.models.base import ProjectStatus, ProjectType, UserRole  # noqa: E402
from app.models.core import Project, User  # noqa: E402
from app.services.field_override_service import FieldOverrideService  # noqa: E402
from app.services.procedure_table_auto_service import ProcedureTableService  # noqa: E402


FAKE_USER_ID = uuid.uuid4()
FAKE_PROJECT_ID = uuid.uuid4()
YEAR = 2025


@pytest_asyncio.fixture
async def db_session():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    """Seed minimal project + user for field_override queries."""
    user = User(
        id=FAKE_USER_ID,
        username="testuser",
        email="test@example.com",
        hashed_password="x",
        role=UserRole.partner,
    )
    db_session.add(user)
    project = Project(
        id=FAKE_PROJECT_ID,
        name="Test Project",
        client_name="Test Client",
        project_type=ProjectType.annual,
        status=ProjectStatus.execution,
        audit_period_start=date(2025, 1, 1),
        audit_period_end=date(2025, 12, 31),
        created_by=FAKE_USER_ID,
    )
    db_session.add(project)
    await db_session.flush()
    return db_session


async def _set_field_override(
    db: AsyncSession,
    project_id: uuid.UUID,
    year: int,
    scope: str,
    item_key: str,
    field: str,
    value: str,
):
    svc = FieldOverrideService(db)
    await svc.set(project_id, year, scope, item_key, field, value, FAKE_USER_ID)


class TestA16SignStatusCheckAuto:
    """a16_sign_status_check auto_data_source 单元测试"""

    @pytest.mark.asyncio
    async def test_signed_suggests_completed(self, db_session, seeded_db):
        """主版本 signed → step_status=completed"""
        await _set_field_override(
            db_session, FAKE_PROJECT_ID, YEAR,
            "word_template:A16", "selected_version", "value", "A16-1"
        )
        await _set_field_override(
            db_session, FAKE_PROJECT_ID, YEAR,
            "word_template:A16:A16-1", "sign_status", "value", "signed"
        )
        await db_session.flush()

        svc = ProcedureTableService(db_session)
        item = {"seq": 9, "auto_data_source": "a16_sign_status_check"}
        result = await svc._resolve_auto_values(FAKE_PROJECT_ID, YEAR, item, "C")

        assert result["step_status"] == "completed"
        assert "已签署" in result["summary"]
        assert "A16-1" in result["summary"]

    @pytest.mark.asyncio
    async def test_sent_suggests_in_progress(self, db_session, seeded_db):
        """主版本 sent → step_status=in_progress"""
        await _set_field_override(
            db_session, FAKE_PROJECT_ID, YEAR,
            "word_template:A16", "selected_version", "value", "A16-3"
        )
        await _set_field_override(
            db_session, FAKE_PROJECT_ID, YEAR,
            "word_template:A16:A16-3", "sign_status", "value", "sent"
        )
        await db_session.flush()

        svc = ProcedureTableService(db_session)
        item = {"seq": 9, "auto_data_source": "a16_sign_status_check"}
        result = await svc._resolve_auto_values(FAKE_PROJECT_ID, YEAR, item, "C")

        assert result["step_status"] == "in_progress"
        assert "已发出" in result["summary"]
        assert "A16-3" in result["summary"]

    @pytest.mark.asyncio
    async def test_pending_no_step_status(self, db_session, seeded_db):
        """主版本 pending → 无 step_status 建议"""
        await _set_field_override(
            db_session, FAKE_PROJECT_ID, YEAR,
            "word_template:A16", "selected_version", "value", "A16-2"
        )
        await _set_field_override(
            db_session, FAKE_PROJECT_ID, YEAR,
            "word_template:A16:A16-2", "sign_status", "value", "pending"
        )
        await db_session.flush()

        svc = ProcedureTableService(db_session)
        item = {"seq": 9, "auto_data_source": "a16_sign_status_check"}
        result = await svc._resolve_auto_values(FAKE_PROJECT_ID, YEAR, item, "C")

        assert "step_status" not in result
        assert "待签署" in result["summary"]
        assert "A16-2" in result["summary"]

    @pytest.mark.asyncio
    async def test_no_selected_version(self, db_session, seeded_db):
        """无 selected_version → 无 step_status，提示待确定"""
        svc = ProcedureTableService(db_session)
        item = {"seq": 9, "auto_data_source": "a16_sign_status_check"}
        result = await svc._resolve_auto_values(FAKE_PROJECT_ID, YEAR, item, "C")

        assert "step_status" not in result
        assert "待确定主版本" in result["summary"]

    @pytest.mark.asyncio
    async def test_selected_version_no_sign_status(self, db_session, seeded_db):
        """有 selected_version 但无 sign_status 记录 → 待签署"""
        await _set_field_override(
            db_session, FAKE_PROJECT_ID, YEAR,
            "word_template:A16", "selected_version", "value", "A16-5"
        )
        await db_session.flush()

        svc = ProcedureTableService(db_session)
        item = {"seq": 9, "auto_data_source": "a16_sign_status_check"}
        result = await svc._resolve_auto_values(FAKE_PROJECT_ID, YEAR, item, "C")

        assert "step_status" not in result
        assert "待签署" in result["summary"]
