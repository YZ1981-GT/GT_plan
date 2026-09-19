"""wp_header_data_service 单元测试

验证表头数据返回正确字段映射，项目不存在时返回空表头。
"""
import asyncio
import uuid
from datetime import date

import pytest
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.base import Base, ProjectStatus, ProjectType, UserRole
from app.models.core import Project, User
from app.models.workpaper_models import WpIndex
from app.services.wp_header_data_service import get_header_data

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
_TABLES = [User.__table__, Project.__table__, WpIndex.__table__]


@pytest.fixture
def db_session():
    """为每个测试创建独立内存 DB"""
    async def _make():
        engine = create_async_engine(TEST_DB_URL, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, tables=_TABLES)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        return factory, engine
    factory, engine = asyncio.get_event_loop().run_until_complete(_make())
    yield factory
    asyncio.get_event_loop().run_until_complete(engine.dispose())


@pytest.mark.asyncio
async def test_header_data_with_project(db_session):
    """项目存在时返回正确表头字段"""
    async with db_session() as session:
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()
        session.add(User(
            id=user_id, username="test", email="t@t.com",
            hashed_password="x", role=UserRole.manager,
        ))
        await session.flush()
        session.add(Project(
            id=project_id,
            name="测试项目",
            client_name="重庆和平药房",
            project_type=ProjectType.annual,
            status=ProjectStatus.execution,
            audit_period_start=date(2025, 1, 1),
            audit_period_end=date(2025, 12, 31),
            audit_year=2025,
            created_by=user_id,
        ))
        await session.flush()

        result = await get_header_data(session, project_id, "A1", wp_name="财务报告程序表")

        assert result["entityName"] == "重庆和平药房"
        assert result["wpName"] == "财务报告程序表"
        assert result["indexNo"] == "A1"
        assert "2025年01月01日" in result["period"]
        assert "2025年12月31日" in result["period"]


@pytest.mark.asyncio
async def test_header_data_project_not_found(db_session):
    """项目不存在时返回空表头"""
    async with db_session() as session:
        result = await get_header_data(session, uuid.uuid4(), "A1")
        assert result["entityName"] == ""
        assert result["indexNo"] == "A1"
        assert result["period"] == ""


@pytest.mark.asyncio
async def test_header_data_no_period(db_session):
    """审计期间为空时自动推导"""
    async with db_session() as session:
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()
        session.add(User(
            id=user_id, username="test2", email="t2@t.com",
            hashed_password="x", role=UserRole.manager,
        ))
        await session.flush()
        session.add(Project(
            id=project_id,
            name="无期间项目",
            client_name="客户A",
            project_type=ProjectType.annual,
            status=ProjectStatus.created,
            audit_year=2024,
            created_by=user_id,
        ))
        await session.flush()

        result = await get_header_data(session, project_id, "E1")
        assert "2024年01月01日" in result["period"]
        assert "2024年12月31日" in result["period"]
