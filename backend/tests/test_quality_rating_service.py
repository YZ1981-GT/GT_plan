"""QualityRatingService 单元测试

Validates: Requirements 3 (Round 3)
- 5 维度评分 + 权重配置
- 评级阈值：A>=90, B>=75, C>=60, D<60
- 人工 override（必须附文字说明）
- 权重从 system_settings 读取
- 批量计算所有项目
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text as sa_text
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.qc_rating_models import ProjectQualityRating

# Import models so they're registered with Base.metadata
import app.models.core  # noqa: F401

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """每个测试独立的内存数据库会话。"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        # 创建 system_settings 表
        await session.execute(
            sa_text(
                "CREATE TABLE IF NOT EXISTS system_settings "
                "(key VARCHAR(100) PRIMARY KEY, value TEXT, "
                "value_type VARCHAR(20), description TEXT)"
            )
        )
        await session.commit()
        yield session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROJECT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


async def _seed_project(db: AsyncSession, project_id: uuid.UUID = PROJECT_ID):
    """插入测试项目。"""
    await db.execute(
        sa_text(
            "INSERT INTO projects (id, name, client_name, is_deleted, status, version, consol_level) "
            "VALUES (:id, :name, :client_name, 0, 'created', 1, 1)"
        ),
        {"id": str(project_id), "name": f"测试项目-{str(project_id)[:8]}", "client_name": "测试客户"},
    )
    await db.flush()


async def _seed_weights(db: AsyncSession, weights: dict[str, float]):
    """插入自定义权重到 system_settings。"""
    await db.execute(
        sa_text(
            "INSERT OR REPLACE INTO system_settings (key, value) "
            "VALUES ('qc_rating_weights', :value)"
        ),
        {"value": json.dumps(weights)},
    )
    await db.flush()


# ---------------------------------------------------------------------------
# 评级阈值测试
# ---------------------------------------------------------------------------


class TestScoreToRating:
    """测试分数到评级的映射。"""

    def test_score_90_is_A(self):
        from app.services.quality_rating_service import QualityRatingService

        assert QualityRatingService._score_to_rating(90) == "A"

    def test_score_95_is_A(self):
        from app.services.quality_rating_service import QualityRatingService

        assert QualityRatingService._score_to_rating(95) == "A"

    def test_score_100_is_A(self):
        from app.services.quality_rating_service import QualityRatingService

        assert QualityRatingService._score_to_rating(100) == "A"

    def test_score_89_is_B(self):
        from app.services.quality_rating_service import QualityRatingService

        assert QualityRatingService._score_to_rating(89) == "B"

    def test_score_75_is_B(self):
        from app.services.quality_rating_service import QualityRatingService

        assert QualityRatingService._score_to_rating(75) == "B"

    def test_score_74_is_C(self):
        from app.services.quality_rating_service import QualityRatingService

        assert QualityRatingService._score_to_rating(74) == "C"

    def test_score_60_is_C(self):
        from app.services.quality_rating_service import QualityRatingService

        assert QualityRatingService._score_to_rating(60) == "C"

    def test_score_59_is_D(self):
        from app.services.quality_rating_service import QualityRatingService

        assert QualityRatingService._score_to_rating(59) == "D"

    def test_score_0_is_D(self):
        from app.services.quality_rating_service import QualityRatingService

        assert QualityRatingService._score_to_rating(0) == "D"


# ---------------------------------------------------------------------------
# 权重配置测试
# ---------------------------------------------------------------------------


class TestWeightsConfig:
    """测试权重配置读取。"""

    @pytest.mark.asyncio
    async def test_default_weights_when_no_config(self, db_session: AsyncSession):
        """system_settings 无配置时使用默认权重。"""
        from app.services.quality_rating_service import (
            DEFAULT_WEIGHTS,
            quality_rating_service,
        )

        weights = await quality_rating_service._get_weights(db_session)
        assert weights == DEFAULT_WEIGHTS

    @pytest.mark.asyncio
    async def test_custom_weights_from_settings(self, db_session: AsyncSession):
        """从 system_settings 读取自定义权重。"""
        from app.services.quality_rating_service import quality_rating_service

        custom_weights = {
            "qc_pass_rate": 0.40,
            "review_depth": 0.20,
            "gate_failures": 0.15,
            "remediation_sla": 0.15,
            "client_response": 0.10,
        }
        await _seed_weights(db_session, custom_weights)

        weights = await quality_rating_service._get_weights(db_session)
        assert weights == custom_weights

    @pytest.mark.asyncio
    async def test_invalid_weights_fallback_to_default(self, db_session: AsyncSession):
        """无效权重配置回退默认值。"""
        from app.services.quality_rating_service import (
            DEFAULT_WEIGHTS,
            quality_rating_service,
        )

        # 只有 3 个维度（不合法）
        await db_session.execute(
            sa_text(
                "INSERT OR REPLACE INTO system_settings (key, value) "
                "VALUES ('qc_rating_weights', :value)"
            ),
            {"value": json.dumps({"a": 0.5, "b": 0.3, "c": 0.2})},
        )
        await db_session.flush()

        weights = await quality_rating_service._get_weights(db_session)
        assert weights == DEFAULT_WEIGHTS


# ---------------------------------------------------------------------------
# 评级计算测试
# ---------------------------------------------------------------------------


class TestComputeRating:
    """测试评级计算。"""

    @pytest.mark.asyncio
    async def test_compute_creates_record(self, db_session: AsyncSession):
        """compute 创建评级记录。"""
        from app.services.quality_rating_service import quality_rating_service

        await _seed_project(db_session)

        result = await quality_rating_service.compute(
            db_session, PROJECT_ID, 2026
        )

        assert result.project_id == PROJECT_ID
        assert result.year == 2026
        assert result.rating in ("A", "B", "C", "D")
        assert 0 <= result.score <= 100
        assert result.dimensions is not None
        assert "qc_pass_rate" in result.dimensions
        assert "review_depth" in result.dimensions
        assert "gate_failures" in result.dimensions
        assert "remediation_sla" in result.dimensions
        assert "client_response" in result.dimensions

    @pytest.mark.asyncio
    async def test_compute_updates_existing_record(self, db_session: AsyncSession):
        """重复计算更新已有记录。"""
        from app.services.quality_rating_service import quality_rating_service

        await _seed_project(db_session)

        # 第一次计算
        result1 = await quality_rating_service.compute(
            db_session, PROJECT_ID, 2026
        )
        await db_session.flush()

        # 第二次计算（应更新而非新建）
        result2 = await quality_rating_service.compute(
            db_session, PROJECT_ID, 2026
        )

        assert result2.id == result1.id

    @pytest.mark.asyncio
    async def test_compute_different_years_separate_records(
        self, db_session: AsyncSession
    ):
        """不同年份创建独立记录。"""
        from app.services.quality_rating_service import quality_rating_service

        await _seed_project(db_session)

        result_2025 = await quality_rating_service.compute(
            db_session, PROJECT_ID, 2025
        )
        await db_session.flush()

        result_2026 = await quality_rating_service.compute(
            db_session, PROJECT_ID, 2026
        )

        assert result_2025.id != result_2026.id
        assert result_2025.year == 2025
        assert result_2026.year == 2026


# ---------------------------------------------------------------------------
# 人工 Override 测试
# ---------------------------------------------------------------------------


class TestOverrideRating:
    """测试人工覆盖评级。"""

    @pytest.mark.asyncio
    async def test_override_existing_rating(self, db_session: AsyncSession):
        """覆盖已有评级。"""
        from app.services.quality_rating_service import quality_rating_service

        await _seed_project(db_session)

        # 先计算
        await quality_rating_service.compute(db_session, PROJECT_ID, 2026)
        await db_session.flush()

        # 覆盖
        result = await quality_rating_service.override_rating(
            db_session,
            project_id=PROJECT_ID,
            year=2026,
            rating="A",
            reason="项目有特殊情况，客户配合度极高",
            override_by=USER_ID,
        )

        assert result["override_rating"] == "A"
        assert result["override_reason"] == "项目有特殊情况，客户配合度极高"
        assert result["override_by"] == str(USER_ID)

    @pytest.mark.asyncio
    async def test_override_creates_record_if_none(self, db_session: AsyncSession):
        """无系统评级时 override 创建空记录。"""
        from app.services.quality_rating_service import quality_rating_service

        result = await quality_rating_service.override_rating(
            db_session,
            project_id=PROJECT_ID,
            year=2026,
            rating="B",
            reason="手动评定",
            override_by=USER_ID,
        )

        assert result["override_rating"] == "B"
        assert result["system_rating"] == "D"  # 默认

    @pytest.mark.asyncio
    async def test_override_invalid_rating_raises(self, db_session: AsyncSession):
        """无效评级抛出 ValueError。"""
        from app.services.quality_rating_service import quality_rating_service

        with pytest.raises(ValueError, match="评级必须为 A/B/C/D"):
            await quality_rating_service.override_rating(
                db_session,
                project_id=PROJECT_ID,
                year=2026,
                rating="E",
                reason="test",
                override_by=USER_ID,
            )

    @pytest.mark.asyncio
    async def test_override_empty_reason_raises(self, db_session: AsyncSession):
        """空原因抛出 ValueError。"""
        from app.services.quality_rating_service import quality_rating_service

        with pytest.raises(ValueError, match="覆盖原因不能为空"):
            await quality_rating_service.override_rating(
                db_session,
                project_id=PROJECT_ID,
                year=2026,
                rating="A",
                reason="",
                override_by=USER_ID,
            )

    @pytest.mark.asyncio
    async def test_override_whitespace_reason_raises(self, db_session: AsyncSession):
        """纯空白原因抛出 ValueError。"""
        from app.services.quality_rating_service import quality_rating_service

        with pytest.raises(ValueError, match="覆盖原因不能为空"):
            await quality_rating_service.override_rating(
                db_session,
                project_id=PROJECT_ID,
                year=2026,
                rating="A",
                reason="   ",
                override_by=USER_ID,
            )


# ---------------------------------------------------------------------------
# 获取评级测试
# ---------------------------------------------------------------------------


class TestGetRating:
    """测试获取评级详情。"""

    @pytest.mark.asyncio
    async def test_get_rating_returns_derivation(self, db_session: AsyncSession):
        """获取评级包含推导过程。"""
        from app.services.quality_rating_service import quality_rating_service

        await _seed_project(db_session)
        await quality_rating_service.compute(db_session, PROJECT_ID, 2026)
        await db_session.flush()

        result = await quality_rating_service.get_rating(
            db_session, PROJECT_ID, 2026
        )

        assert result is not None
        assert "derivation" in result
        assert len(result["derivation"]) == 5
        assert "weights" in result
        assert "dimensions" in result

    @pytest.mark.asyncio
    async def test_get_rating_nonexistent_returns_none(
        self, db_session: AsyncSession
    ):
        """不存在的评级返回 None。"""
        from app.services.quality_rating_service import quality_rating_service

        result = await quality_rating_service.get_rating(
            db_session, uuid.uuid4(), 2026
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_get_rating_shows_override(self, db_session: AsyncSession):
        """获取评级显示 override 信息。"""
        from app.services.quality_rating_service import quality_rating_service

        await _seed_project(db_session)
        await quality_rating_service.compute(db_session, PROJECT_ID, 2026)
        await db_session.flush()

        await quality_rating_service.override_rating(
            db_session,
            project_id=PROJECT_ID,
            year=2026,
            rating="A",
            reason="特殊情况",
            override_by=USER_ID,
        )
        await db_session.flush()

        result = await quality_rating_service.get_rating(
            db_session, PROJECT_ID, 2026
        )

        # rating 字段应返回 override 后的值
        assert result["rating"] == "A"
        assert result["override_rating"] == "A"
        assert result["override_reason"] == "特殊情况"


# ---------------------------------------------------------------------------
# 批量计算测试
# ---------------------------------------------------------------------------


class TestComputeAllProjects:
    """测试批量计算。"""

    @pytest.mark.asyncio
    async def test_compute_all_projects(self, db_session: AsyncSession):
        """批量计算所有项目。"""
        from app.services.quality_rating_service import quality_rating_service

        # 创建 3 个项目
        pids = [uuid.uuid4() for _ in range(3)]
        for pid in pids:
            await _seed_project(db_session, pid)
        await db_session.flush()

        count = await quality_rating_service.compute_all_projects(
            db_session, 2026
        )

        assert count == 3

    @pytest.mark.asyncio
    async def test_compute_all_projects_empty(self, db_session: AsyncSession):
        """无项目时返回 0。"""
        from app.services.quality_rating_service import quality_rating_service

        count = await quality_rating_service.compute_all_projects(
            db_session, 2026
        )
        assert count == 0


# ---------------------------------------------------------------------------
# 推导过程测试
# ---------------------------------------------------------------------------


class TestDerivation:
    """测试推导过程构建。"""

    def test_build_derivation_correct_structure(self):
        """推导过程结构正确。"""
        from app.services.quality_rating_service import QualityRatingService

        dims = {
            "qc_pass_rate": 85.0,
            "review_depth": 72.0,
            "gate_failures": 90.0,
            "remediation_sla": 65.0,
            "client_response": 80.0,
        }
        weights = {
            "qc_pass_rate": 0.30,
            "review_depth": 0.25,
            "gate_failures": 0.20,
            "remediation_sla": 0.15,
            "client_response": 0.10,
        }

        derivation = QualityRatingService._build_derivation(dims, weights)

        assert len(derivation) == 5
        for item in derivation:
            assert "dimension" in item
            assert "weight" in item
            assert "score" in item
            assert "weighted_score" in item

        # 验证加权分计算
        qc_item = next(d for d in derivation if d["dimension"] == "qc_pass_rate")
        assert qc_item["weighted_score"] == round(0.30 * 85.0, 2)

    def test_build_derivation_empty_dimensions(self):
        """空维度返回空列表。"""
        from app.services.quality_rating_service import QualityRatingService

        derivation = QualityRatingService._build_derivation(None, {})
        assert derivation == []
