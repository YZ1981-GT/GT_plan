# -*- coding: utf-8 -*-
"""Tests for Task 24: 保留期 + 轮换检查

验证：
1. rotation_check_service 连续年数计算
2. data_lifecycle_service.purge_project_data 保留期校验
3. ArchiveOrchestrator 归档成功后写 archived_at + retention_until
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.models.core  # noqa: F401
import app.models.audit_platform_models  # noqa: F401
import app.models.archive_models  # noqa: F401
import app.models.staff_models  # noqa: F401
import app.models.rotation_models  # noqa: F401
from app.models.base import Base
from app.models.core import Project
from app.models.staff_models import ProjectAssignment
from app.models.rotation_models import PartnerRotationOverride
from app.services.rotation_check_service import RotationCheckService
from app.services.data_lifecycle_service import DataLifecycleService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

FAKE_STAFF_ID = uuid.uuid4()
FAKE_PROJECT_ID = uuid.uuid4()
CLIENT_NAME = "测试客户有限公司"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


# ---------------------------------------------------------------------------
# rotation_check_service tests
# ---------------------------------------------------------------------------


class TestRotationCheckService:
    """测试轮换检查服务"""

    @pytest.mark.asyncio
    async def test_no_assignments_returns_zero(self, db_session: AsyncSession):
        """无委派记录时连续年数为 0"""
        svc = RotationCheckService(db_session)
        result = await svc.check_rotation(FAKE_STAFF_ID, CLIENT_NAME)
        assert result["continuous_years"] == 0
        assert result["years_served"] == []
        assert result["current_override_id"] is None

    @pytest.mark.asyncio
    async def test_continuous_years_calculation(self, db_session: AsyncSession):
        """连续 3 年委派应返回 continuous_years=3"""
        # 创建项目和委派
        for year in [2023, 2024, 2025]:
            project_id = uuid.uuid4()
            project = Project(
                id=project_id,
                name=f"项目{year}",
                client_name=CLIENT_NAME,
                audit_period_start=date(year, 1, 1),
                audit_period_end=date(year, 12, 31),
            )
            db_session.add(project)
            assignment = ProjectAssignment(
                id=uuid.uuid4(),
                project_id=project_id,
                staff_id=FAKE_STAFF_ID,
                role="signing_partner",
            )
            db_session.add(assignment)

        await db_session.flush()

        svc = RotationCheckService(db_session)
        result = await svc.check_rotation(FAKE_STAFF_ID, CLIENT_NAME)
        assert result["continuous_years"] == 3
        assert sorted(result["years_served"]) == [2023, 2024, 2025]

    @pytest.mark.asyncio
    async def test_gap_breaks_continuity(self, db_session: AsyncSession):
        """中间有间隔年时连续年数中断"""
        # 2021, 2022, 2024, 2025 → 连续 2 年（2024-2025）
        for year in [2021, 2022, 2024, 2025]:
            project_id = uuid.uuid4()
            project = Project(
                id=project_id,
                name=f"项目{year}",
                client_name=CLIENT_NAME,
                audit_period_start=date(year, 1, 1),
                audit_period_end=date(year, 12, 31),
            )
            db_session.add(project)
            assignment = ProjectAssignment(
                id=uuid.uuid4(),
                project_id=project_id,
                staff_id=FAKE_STAFF_ID,
                role="signing_partner",
            )
            db_session.add(assignment)

        await db_session.flush()

        svc = RotationCheckService(db_session)
        result = await svc.check_rotation(FAKE_STAFF_ID, CLIENT_NAME)
        assert result["continuous_years"] == 2

    @pytest.mark.asyncio
    async def test_different_client_not_counted(self, db_session: AsyncSession):
        """不同客户的委派不计入"""
        project_id = uuid.uuid4()
        project = Project(
            id=project_id,
            name="其他客户项目",
            client_name="其他客户",
            audit_period_start=date(2025, 1, 1),
            audit_period_end=date(2025, 12, 31),
        )
        db_session.add(project)
        assignment = ProjectAssignment(
            id=uuid.uuid4(),
            project_id=project_id,
            staff_id=FAKE_STAFF_ID,
            role="signing_partner",
        )
        db_session.add(assignment)
        await db_session.flush()

        svc = RotationCheckService(db_session)
        result = await svc.check_rotation(FAKE_STAFF_ID, CLIENT_NAME)
        assert result["continuous_years"] == 0

    @pytest.mark.asyncio
    async def test_eqcr_role_counted(self, db_session: AsyncSession):
        """eqcr 角色也计入轮换年数"""
        project_id = uuid.uuid4()
        project = Project(
            id=project_id,
            name="EQCR项目",
            client_name=CLIENT_NAME,
            audit_period_start=date(2025, 1, 1),
            audit_period_end=date(2025, 12, 31),
        )
        db_session.add(project)
        assignment = ProjectAssignment(
            id=uuid.uuid4(),
            project_id=project_id,
            staff_id=FAKE_STAFF_ID,
            role="eqcr",
        )
        db_session.add(assignment)
        await db_session.flush()

        svc = RotationCheckService(db_session)
        result = await svc.check_rotation(FAKE_STAFF_ID, CLIENT_NAME)
        assert result["continuous_years"] == 1

    @pytest.mark.asyncio
    async def test_active_override_returned(self, db_session: AsyncSession):
        """有效的 override 应返回其 ID"""
        override = PartnerRotationOverride(
            id=uuid.uuid4(),
            staff_id=FAKE_STAFF_ID,
            client_name=CLIENT_NAME,
            original_years=5,
            override_reason="特殊情况",
            approved_by_compliance_partner=uuid.uuid4(),
            approved_by_chief_risk_partner=uuid.uuid4(),
            override_expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        )
        db_session.add(override)
        await db_session.flush()

        svc = RotationCheckService(db_session)
        result = await svc.check_rotation(FAKE_STAFF_ID, CLIENT_NAME)
        assert result["current_override_id"] == str(override.id)

    @pytest.mark.asyncio
    async def test_expired_override_not_returned(self, db_session: AsyncSession):
        """过期的 override 不应返回"""
        override = PartnerRotationOverride(
            id=uuid.uuid4(),
            staff_id=FAKE_STAFF_ID,
            client_name=CLIENT_NAME,
            original_years=5,
            override_reason="已过期",
            approved_by_compliance_partner=uuid.uuid4(),
            approved_by_chief_risk_partner=uuid.uuid4(),
            override_expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        db_session.add(override)
        await db_session.flush()

        svc = RotationCheckService(db_session)
        result = await svc.check_rotation(FAKE_STAFF_ID, CLIENT_NAME)
        assert result["current_override_id"] is None


# ---------------------------------------------------------------------------
# data_lifecycle_service retention check tests
# ---------------------------------------------------------------------------


class TestRetentionCheck:
    """测试保留期校验"""

    @pytest.mark.asyncio
    async def test_purge_blocked_by_retention(self, db_session: AsyncSession):
        """保留期内 purge 应返回 403 RETENTION_LOCKED"""
        from fastapi import HTTPException

        # 创建一个有保留期的项目
        project = Project(
            id=FAKE_PROJECT_ID,
            name="保留期项目",
            client_name=CLIENT_NAME,
            retention_until=datetime.utcnow() + timedelta(days=3652),
        )
        db_session.add(project)
        await db_session.flush()

        svc = DataLifecycleService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await svc.purge_project_data(FAKE_PROJECT_ID)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["error_code"] == "RETENTION_LOCKED"

    @pytest.mark.asyncio
    async def test_purge_allowed_after_retention(self, db_session: AsyncSession):
        """保留期过后 purge 应正常执行"""
        project = Project(
            id=FAKE_PROJECT_ID,
            name="过期项目",
            client_name=CLIENT_NAME,
            retention_until=datetime.utcnow() - timedelta(days=1),
        )
        db_session.add(project)
        await db_session.flush()

        svc = DataLifecycleService(db_session)
        # 不应抛异常（即使没有数据可删）
        result = await svc.purge_project_data(FAKE_PROJECT_ID)
        assert "purged" in result

    @pytest.mark.asyncio
    async def test_purge_allowed_without_retention(self, db_session: AsyncSession):
        """无保留期的项目 purge 应正常执行"""
        project = Project(
            id=FAKE_PROJECT_ID,
            name="无保留期项目",
            client_name=CLIENT_NAME,
            retention_until=None,
        )
        db_session.add(project)
        await db_session.flush()

        svc = DataLifecycleService(db_session)
        result = await svc.purge_project_data(FAKE_PROJECT_ID)
        assert "purged" in result


# ---------------------------------------------------------------------------
# ArchiveOrchestrator retention writing tests
# ---------------------------------------------------------------------------


class TestArchiveRetentionWriting:
    """测试归档成功后写入 archived_at + retention_until"""

    @pytest.mark.asyncio
    async def test_orchestrate_sets_retention(self, db_session: AsyncSession):
        """归档成功后 Project 应有 archived_at 和 retention_until"""
        from app.models.archive_models import ArchiveJob
        from app.services.archive_orchestrator import ArchiveOrchestrator

        # 创建项目
        project = Project(
            id=FAKE_PROJECT_ID,
            name="归档项目",
            client_name=CLIENT_NAME,
        )
        db_session.add(project)
        await db_session.flush()

        orchestrator = ArchiveOrchestrator(db_session)

        # Mock 所有步骤
        with patch.object(orchestrator, "_step_gate", new_callable=AsyncMock), \
             patch.object(orchestrator, "_step_wp_storage", new_callable=AsyncMock), \
             patch.object(orchestrator, "_persist_integrity_hashes", new_callable=AsyncMock), \
             patch.object(orchestrator, "_notify_project_members", new_callable=AsyncMock):

            job = await orchestrator.orchestrate(
                project_id=FAKE_PROJECT_ID,
                scope="final",
                push_to_cloud=False,
                purge_local=False,
            )

        assert job.status == "succeeded"

        # 验证 Project 的 archived_at 和 retention_until 已设置
        from sqlalchemy import select
        stmt = select(Project).where(Project.id == FAKE_PROJECT_ID)
        result = await db_session.execute(stmt)
        updated_project = result.scalar_one()

        assert updated_project.archived_at is not None
        assert updated_project.retention_until is not None
        # retention_until 应约为 archived_at + 10 年
        diff = updated_project.retention_until - updated_project.archived_at
        assert 3650 <= diff.days <= 3653  # ~10 years



# ---------------------------------------------------------------------------
# Batch 2-2: rotation_limit listed/unlisted tests (R1 Bug Fix 6 retrospective)
# ---------------------------------------------------------------------------


class TestRotationLimitListedUnlisted:
    """Fix 6: 验证 is_listed_company / system_settings 对 rotation_limit 的影响。"""

    @pytest.mark.asyncio
    async def test_check_rotation_listed_company_default_5y(self, db_session: AsyncSession):
        """默认 is_listed_company=True 返回 rotation_limit=5。"""
        svc = RotationCheckService(db_session)
        result = await svc.check_rotation(FAKE_STAFF_ID, CLIENT_NAME)
        # 默认上市公司 5 年
        assert result["rotation_limit"] == 5

    @pytest.mark.asyncio
    async def test_check_rotation_unlisted_company_7y(self, db_session: AsyncSession):
        """is_listed_company=False 返回 rotation_limit=7。"""
        svc = RotationCheckService(db_session)
        result = await svc.check_rotation(
            FAKE_STAFF_ID, CLIENT_NAME, is_listed_company=False
        )
        assert result["rotation_limit"] == 7

    @pytest.mark.asyncio
    async def test_rotation_limit_reads_system_settings(self, db_session: AsyncSession):
        """有 system_settings 配置时使用配置值（上市覆盖默认 5）。"""
        # 创建 system_settings 表并插入配置（_get_rotation_limit 用 sqlalchemy.text）
        from sqlalchemy import text as sa_text

        # 建表（SQLite 测试环境）
        await db_session.execute(
            sa_text(
                "CREATE TABLE IF NOT EXISTS system_settings "
                "(key VARCHAR(100) PRIMARY KEY, value TEXT)"
            )
        )
        await db_session.execute(
            sa_text(
                "INSERT INTO system_settings (key, value) VALUES "
                "('rotation_limit_listed', '4')"
            )
        )
        await db_session.flush()

        svc = RotationCheckService(db_session)
        result = await svc.check_rotation(
            FAKE_STAFF_ID, CLIENT_NAME, is_listed_company=True
        )
        # 应读取到配置的 4 年（覆盖默认 5）
        assert result["rotation_limit"] == 4
