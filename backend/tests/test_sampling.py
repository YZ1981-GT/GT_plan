"""Tests for Task 23: 抽样记录管理

Tests cover:
- SamplingConfig CRUD
- Sample size calculation (attribute, MUS, random)
- SamplingRecord CRUD
- MUS evaluation calculation
- Completeness check
- API endpoints

Validates: Requirements 11.1-11.6, 12.1-12.2
"""

import math
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType
from app.models.workpaper_models import (
    SamplingConfig,
    SamplingRecord,
    WpFileStatus,
    WpIndex,
    WpSourceType,
    WpStatus,
    WorkingPaper,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

FAKE_USER_ID = uuid.uuid4()
FAKE_PROJECT_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    """Create test data: project + wp_index + working_paper"""
    project = Project(
        id=FAKE_PROJECT_ID,
        name="抽样测试项目",
        client_name="测试客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=FAKE_USER_ID,
    )
    db_session.add(project)
    await db_session.flush()

    idx = WpIndex(
        project_id=FAKE_PROJECT_ID,
        wp_code="E1-1",
        wp_name="货币资金底稿",
        audit_cycle="E",
        status=WpStatus.in_progress,
    )
    db_session.add(idx)
    await db_session.flush()

    wp = WorkingPaper(
        project_id=FAKE_PROJECT_ID,
        wp_index_id=idx.id,
        file_path=f"{FAKE_PROJECT_ID}/2025/E1-1.xlsx",
        source_type=WpSourceType.template,
        status=WpFileStatus.draft,
        file_version=1,
        created_by=FAKE_USER_ID,
    )
    db_session.add(wp)
    await db_session.commit()

    return {
        "project_id": FAKE_PROJECT_ID,
        "idx": idx,
        "wp": wp,
    }


# ===================================================================
# SamplingService — Sample Size Calculation
# ===================================================================


class TestSampleSizeCalculation:
    """Tests for sample size calculation formulas."""

    @pytest.mark.asyncio
    async def test_attribute_basic(self):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()
        # 95% confidence → cf=3.0, tdr=0.05, edr=0
        # sample_size = ceil(3.0 / 0.05) = 60
        size = await svc.calculate_sample_size("attribute", {
            "confidence_level": 0.95,
            "tolerable_deviation_rate": 0.05,
        })
        assert size == 60

    @pytest.mark.asyncio
    async def test_attribute_with_expected_deviation(self):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()
        # cf=3.0, tdr=0.05, edr=0.01 → ceil(3.0 / 0.04) = 75
        size = await svc.calculate_sample_size("attribute", {
            "confidence_level": 0.95,
            "tolerable_deviation_rate": 0.05,
            "expected_deviation_rate": 0.01,
        })
        assert size == 75

    @pytest.mark.asyncio
    async def test_attribute_90_confidence(self):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()
        # 90% → cf=2.3, tdr=0.05 → ceil(2.3/0.05) = 46
        size = await svc.calculate_sample_size("attribute", {
            "confidence_level": 0.90,
            "tolerable_deviation_rate": 0.05,
        })
        assert size == 46

    @pytest.mark.asyncio
    async def test_attribute_with_finite_population(self):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()
        # cf=3.0, tdr=0.05 → n0=60, N=100 → adj = ceil(60/(1+60/100)) = ceil(37.5) = 38
        size = await svc.calculate_sample_size("attribute", {
            "confidence_level": 0.95,
            "tolerable_deviation_rate": 0.05,
            "population_count": 100,
        })
        assert size == 38

    @pytest.mark.asyncio
    async def test_attribute_invalid_tdr_zero(self):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()
        with pytest.raises(ValueError, match="可容忍偏差率必须大于0"):
            await svc.calculate_sample_size("attribute", {
                "tolerable_deviation_rate": 0,
            })

    @pytest.mark.asyncio
    async def test_attribute_edr_exceeds_tdr(self):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()
        with pytest.raises(ValueError, match="可容忍偏差率必须大于预期偏差率"):
            await svc.calculate_sample_size("attribute", {
                "tolerable_deviation_rate": 0.02,
                "expected_deviation_rate": 0.03,
            })

    @pytest.mark.asyncio
    async def test_mus_basic(self):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()
        # cf=3.0, pop=1_000_000, tm=50_000 → ceil(1000000*3.0/50000) = 60
        size = await svc.calculate_sample_size("mus", {
            "confidence_level": 0.95,
            "population_amount": 1_000_000,
            "tolerable_misstatement": 50_000,
        })
        assert size == 60

    @pytest.mark.asyncio
    async def test_mus_99_confidence(self):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()
        # cf=4.6, pop=1_000_000, tm=50_000 → ceil(1000000*4.6/50000) = 92
        size = await svc.calculate_sample_size("mus", {
            "confidence_level": 0.99,
            "population_amount": 1_000_000,
            "tolerable_misstatement": 50_000,
        })
        assert size == 92

    @pytest.mark.asyncio
    async def test_mus_invalid_zero_amount(self):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()
        with pytest.raises(ValueError, match="总体金额必须大于0"):
            await svc.calculate_sample_size("mus", {
                "population_amount": 0,
                "tolerable_misstatement": 50_000,
            })

    @pytest.mark.asyncio
    async def test_mus_invalid_zero_misstatement(self):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()
        with pytest.raises(ValueError, match="可容忍错报必须大于0"):
            await svc.calculate_sample_size("mus", {
                "population_amount": 1_000_000,
                "tolerable_misstatement": 0,
            })

    @pytest.mark.asyncio
    async def test_random_with_specified_size(self):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()
        size = await svc.calculate_sample_size("random", {"sample_size": 50})
        assert size == 50

    @pytest.mark.asyncio
    async def test_random_with_population(self):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()
        size = await svc.calculate_sample_size("random", {
            "confidence_level": 0.95,
            "population_count": 1000,
        })
        # cf=3.0, sqrt(1000)≈31.6 → ceil(3.0*31.6) = 95
        assert size == math.ceil(3.0 * math.sqrt(1000))

    @pytest.mark.asyncio
    async def test_systematic_fallback(self):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()
        size = await svc.calculate_sample_size("systematic", {})
        assert size == 30  # default fallback

    @pytest.mark.asyncio
    async def test_unsupported_method(self):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()
        with pytest.raises(ValueError, match="不支持的抽样方法"):
            await svc.calculate_sample_size("unknown", {})


# ===================================================================
# SamplingService — Config CRUD
# ===================================================================


class TestSamplingConfigCRUD:
    """Tests for SamplingConfig create/list/update."""

    @pytest.mark.asyncio
    async def test_create_config(self, db_session, seeded_db):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()
        result = await svc.create_config(
            db=db_session,
            project_id=FAKE_PROJECT_ID,
            data={
                "config_name": "MUS抽样配置",
                "sampling_type": "statistical",
                "sampling_method": "mus",
                "applicable_scenario": "substantive_test",
                "confidence_level": 0.95,
                "population_amount": 1_000_000,
                "tolerable_misstatement": 50_000,
            },
        )
        assert result["config_name"] == "MUS抽样配置"
        assert result["sampling_method"] == "mus"
        assert result["calculated_sample_size"] == 60

    @pytest.mark.asyncio
    async def test_create_config_auto_calc_attribute(self, db_session, seeded_db):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()
        result = await svc.create_config(
            db=db_session,
            project_id=FAKE_PROJECT_ID,
            data={
                "config_name": "属性抽样配置",
                "sampling_type": "statistical",
                "sampling_method": "attribute",
                "applicable_scenario": "control_test",
                "confidence_level": 0.95,
                "tolerable_deviation_rate": 0.05,
            },
        )
        assert result["calculated_sample_size"] == 60

    @pytest.mark.asyncio
    async def test_list_configs(self, db_session, seeded_db):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()
        await svc.create_config(db=db_session, project_id=FAKE_PROJECT_ID, data={
            "config_name": "配置1", "sampling_type": "statistical",
            "sampling_method": "random", "applicable_scenario": "substantive_test",
        })
        await svc.create_config(db=db_session, project_id=FAKE_PROJECT_ID, data={
            "config_name": "配置2", "sampling_type": "non_statistical",
            "sampling_method": "systematic", "applicable_scenario": "control_test",
        })
        await db_session.commit()

        items = await svc.list_configs(db=db_session, project_id=FAKE_PROJECT_ID)
        assert len(items) == 2
        assert items[0]["config_name"] == "配置1"
        assert items[1]["config_name"] == "配置2"

    @pytest.mark.asyncio
    async def test_update_config(self, db_session, seeded_db):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()
        created = await svc.create_config(db=db_session, project_id=FAKE_PROJECT_ID, data={
            "config_name": "原始配置", "sampling_type": "statistical",
            "sampling_method": "mus", "applicable_scenario": "substantive_test",
            "confidence_level": 0.95, "population_amount": 1_000_000,
            "tolerable_misstatement": 50_000,
        })
        await db_session.commit()

        updated = await svc.update_config(
            db=db_session,
            config_id=uuid.UUID(created["id"]),
            data={"config_name": "更新后配置", "tolerable_misstatement": 100_000},
        )
        assert updated["config_name"] == "更新后配置"
        # Recalculated: ceil(1000000*3.0/100000) = 30
        assert updated["calculated_sample_size"] == 30

    @pytest.mark.asyncio
    async def test_update_config_not_found(self, db_session, seeded_db):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()
        with pytest.raises(ValueError, match="抽样配置不存在"):
            await svc.update_config(db=db_session, config_id=uuid.uuid4(), data={})


# ===================================================================
# SamplingService — Record CRUD
# ===================================================================


class TestSamplingRecordCRUD:
    """Tests for SamplingRecord create/list/update."""

    @pytest.mark.asyncio
    async def test_create_record(self, db_session, seeded_db):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()
        result = await svc.create_record(
            db=db_session,
            project_id=FAKE_PROJECT_ID,
            data={
                "working_paper_id": str(seeded_db["wp"].id),
                "sampling_purpose": "测试应收账款函证",
                "population_description": "应收账款明细",
                "population_total_amount": 5_000_000,
                "population_total_count": 200,
                "sample_size": 30,
                "conclusion": "未发现重大偏差",
            },
        )
        assert result["sampling_purpose"] == "测试应收账款函证"
        assert result["sample_size"] == 30
        assert result["conclusion"] == "未发现重大偏差"

    @pytest.mark.asyncio
    async def test_list_records(self, db_session, seeded_db):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()
        await svc.create_record(db=db_session, project_id=FAKE_PROJECT_ID, data={
            "sampling_purpose": "记录1", "population_description": "总体1", "sample_size": 10,
        })
        await svc.create_record(db=db_session, project_id=FAKE_PROJECT_ID, data={
            "sampling_purpose": "记录2", "population_description": "总体2", "sample_size": 20,
        })
        await db_session.commit()

        items = await svc.list_records(db=db_session, project_id=FAKE_PROJECT_ID)
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_list_records_filter_by_wp(self, db_session, seeded_db):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()
        wp_id = seeded_db["wp"].id
        await svc.create_record(db=db_session, project_id=FAKE_PROJECT_ID, data={
            "working_paper_id": str(wp_id),
            "sampling_purpose": "关联底稿", "population_description": "总体", "sample_size": 10,
        })
        await svc.create_record(db=db_session, project_id=FAKE_PROJECT_ID, data={
            "sampling_purpose": "无关联", "population_description": "总体", "sample_size": 20,
        })
        await db_session.commit()

        filtered = await svc.list_records(db=db_session, project_id=FAKE_PROJECT_ID, working_paper_id=wp_id)
        assert len(filtered) == 1
        assert filtered[0]["sampling_purpose"] == "关联底稿"

    @pytest.mark.asyncio
    async def test_update_record(self, db_session, seeded_db):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()
        created = await svc.create_record(db=db_session, project_id=FAKE_PROJECT_ID, data={
            "sampling_purpose": "原始", "population_description": "总体", "sample_size": 10,
        })
        await db_session.commit()

        updated = await svc.update_record(
            db=db_session,
            record_id=uuid.UUID(created["id"]),
            data={"conclusion": "已完成", "deviations_found": 2},
        )
        assert updated["conclusion"] == "已完成"
        assert updated["deviations_found"] == 2

    @pytest.mark.asyncio
    async def test_update_record_not_found(self, db_session, seeded_db):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()
        with pytest.raises(ValueError, match="抽样记录不存在"):
            await svc.update_record(db=db_session, record_id=uuid.uuid4(), data={})


# ===================================================================
# SamplingService — MUS Evaluation
# ===================================================================


class TestMUSEvaluation:
    """Tests for MUS evaluation calculation."""

    @pytest.mark.asyncio
    async def test_mus_evaluation_basic(self, db_session, seeded_db):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()

        # Create config with 95% confidence
        config = await svc.create_config(db=db_session, project_id=FAKE_PROJECT_ID, data={
            "config_name": "MUS配置", "sampling_type": "statistical",
            "sampling_method": "mus", "applicable_scenario": "substantive_test",
            "confidence_level": 0.95,
            "population_amount": 1_000_000,
            "tolerable_misstatement": 50_000,
        })
        await db_session.flush()

        # Create record linked to config
        record = await svc.create_record(db=db_session, project_id=FAKE_PROJECT_ID, data={
            "sampling_config_id": config["id"],
            "sampling_purpose": "MUS测试",
            "population_description": "应收账款",
            "population_total_amount": 1_000_000,
            "sample_size": 60,
        })
        await db_session.flush()

        # Evaluate with one misstatement
        result = await svc.calculate_mus_evaluation(
            db=db_session,
            record_id=uuid.UUID(record["id"]),
            misstatement_details=[
                {"book_value": 10000, "misstatement_amount": 500},
            ],
        )

        # sampling_interval = 1_000_000 / 60 ≈ 16666.67
        # tainting_factor = 500 / 10000 = 0.05
        # projected = 0.05 * 16666.67 ≈ 833.33
        # basic_precision = 16666.67 * 3.0 = 50000
        # upper_limit = 833.33 + 50000 ≈ 50833.33
        assert result["projected_misstatement"] > 0
        assert result["upper_misstatement_limit"] > result["projected_misstatement"]
        assert len(result["details"]) == 1
        assert result["details"][0]["tainting_factor"] == 0.05

    @pytest.mark.asyncio
    async def test_mus_evaluation_no_misstatements(self, db_session, seeded_db):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()

        record = await svc.create_record(db=db_session, project_id=FAKE_PROJECT_ID, data={
            "sampling_purpose": "MUS无错报",
            "population_description": "应收账款",
            "population_total_amount": 1_000_000,
            "sample_size": 60,
        })
        await db_session.flush()

        result = await svc.calculate_mus_evaluation(
            db=db_session,
            record_id=uuid.UUID(record["id"]),
            misstatement_details=[],
        )

        assert result["projected_misstatement"] == 0
        # upper_limit = basic_precision only
        assert result["upper_misstatement_limit"] > 0

    @pytest.mark.asyncio
    async def test_mus_evaluation_multiple_misstatements(self, db_session, seeded_db):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()

        record = await svc.create_record(db=db_session, project_id=FAKE_PROJECT_ID, data={
            "sampling_purpose": "MUS多错报",
            "population_description": "应收账款",
            "population_total_amount": 1_000_000,
            "sample_size": 50,
        })
        await db_session.flush()

        result = await svc.calculate_mus_evaluation(
            db=db_session,
            record_id=uuid.UUID(record["id"]),
            misstatement_details=[
                {"book_value": 10000, "misstatement_amount": 500},
                {"book_value": 20000, "misstatement_amount": 1000},
            ],
        )

        assert len(result["details"]) == 2
        assert result["projected_misstatement"] > 0
        assert result["upper_misstatement_limit"] > result["projected_misstatement"]

    @pytest.mark.asyncio
    async def test_mus_evaluation_zero_book_value(self, db_session, seeded_db):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()

        record = await svc.create_record(db=db_session, project_id=FAKE_PROJECT_ID, data={
            "sampling_purpose": "MUS零账面",
            "population_description": "应收账款",
            "population_total_amount": 1_000_000,
            "sample_size": 50,
        })
        await db_session.flush()

        result = await svc.calculate_mus_evaluation(
            db=db_session,
            record_id=uuid.UUID(record["id"]),
            misstatement_details=[
                {"book_value": 0, "misstatement_amount": 500},
            ],
        )

        # tainting_factor = 1.0 when book_value is 0 and misstatement != 0
        assert result["details"][0]["tainting_factor"] == 1.0

    @pytest.mark.asyncio
    async def test_mus_evaluation_record_not_found(self, db_session, seeded_db):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()
        with pytest.raises(ValueError, match="抽样记录不存在"):
            await svc.calculate_mus_evaluation(
                db=db_session, record_id=uuid.uuid4(), misstatement_details=[],
            )

    @pytest.mark.asyncio
    async def test_mus_evaluation_invalid_population(self, db_session, seeded_db):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()

        record = await svc.create_record(db=db_session, project_id=FAKE_PROJECT_ID, data={
            "sampling_purpose": "MUS无效",
            "population_description": "应收账款",
            "sample_size": 50,
        })
        await db_session.flush()

        with pytest.raises(ValueError, match="总体金额和样本量必须大于0"):
            await svc.calculate_mus_evaluation(
                db=db_session,
                record_id=uuid.UUID(record["id"]),
                misstatement_details=[],
            )


# ===================================================================
# SamplingService — Completeness Check
# ===================================================================


class TestCompletenessCheck:
    """Tests for sampling record completeness check (QC Rule 10)."""

    @pytest.mark.asyncio
    async def test_complete_no_records(self, db_session, seeded_db):
        """No sampling records → considered complete."""
        from app.services.sampling_service import SamplingService
        svc = SamplingService()
        result = await svc.check_completeness(db=db_session, working_paper_id=seeded_db["wp"].id)
        assert result is True

    @pytest.mark.asyncio
    async def test_complete_all_fields_filled(self, db_session, seeded_db):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()
        await svc.create_record(db=db_session, project_id=FAKE_PROJECT_ID, data={
            "working_paper_id": str(seeded_db["wp"].id),
            "sampling_purpose": "测试目的",
            "population_description": "总体描述",
            "sample_size": 30,
            "conclusion": "结论",
        })
        await db_session.commit()

        result = await svc.check_completeness(db=db_session, working_paper_id=seeded_db["wp"].id)
        assert result is True

    @pytest.mark.asyncio
    async def test_incomplete_missing_purpose(self, db_session, seeded_db):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()
        await svc.create_record(db=db_session, project_id=FAKE_PROJECT_ID, data={
            "working_paper_id": str(seeded_db["wp"].id),
            "sampling_purpose": "",
            "population_description": "总体描述",
            "sample_size": 30,
            "conclusion": "结论",
        })
        await db_session.commit()

        result = await svc.check_completeness(db=db_session, working_paper_id=seeded_db["wp"].id)
        assert result is False

    @pytest.mark.asyncio
    async def test_incomplete_missing_conclusion(self, db_session, seeded_db):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()
        await svc.create_record(db=db_session, project_id=FAKE_PROJECT_ID, data={
            "working_paper_id": str(seeded_db["wp"].id),
            "sampling_purpose": "测试目的",
            "population_description": "总体描述",
            "sample_size": 30,
        })
        await db_session.commit()

        result = await svc.check_completeness(db=db_session, working_paper_id=seeded_db["wp"].id)
        assert result is False

    @pytest.mark.asyncio
    async def test_incomplete_zero_sample_size(self, db_session, seeded_db):
        from app.services.sampling_service import SamplingService
        svc = SamplingService()
        await svc.create_record(db=db_session, project_id=FAKE_PROJECT_ID, data={
            "working_paper_id": str(seeded_db["wp"].id),
            "sampling_purpose": "测试目的",
            "population_description": "总体描述",
            "sample_size": 0,
            "conclusion": "结论",
        })
        await db_session.commit()

        result = await svc.check_completeness(db=db_session, working_paper_id=seeded_db["wp"].id)
        assert result is False


# ===================================================================
# API Route Tests
# ===================================================================


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, seeded_db):
    """Create test HTTP client."""
    import fakeredis.aioredis
    from httpx import ASGITransport, AsyncClient
    from app.core.database import get_db
    from app.core.redis import get_redis
    from app.main import app

    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def override_get_db():
        yield db_session

    async def override_get_redis():
        yield fake_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


class TestSamplingConfigAPI:
    """API route tests for sampling config endpoints."""

    @pytest.mark.asyncio
    async def test_create_config_api(self, client, seeded_db):
        resp = await client.post(
            f"/api/projects/{FAKE_PROJECT_ID}/sampling-configs",
            json={
                "config_name": "API测试配置",
                "sampling_type": "statistical",
                "sampling_method": "mus",
                "applicable_scenario": "substantive_test",
                "confidence_level": 0.95,
                "population_amount": 1000000,
                "tolerable_misstatement": 50000,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        result = data.get("data", data)
        assert result["config_name"] == "API测试配置"
        assert result["calculated_sample_size"] == 60

    @pytest.mark.asyncio
    async def test_list_configs_api(self, client, seeded_db):
        # Create one first
        await client.post(
            f"/api/projects/{FAKE_PROJECT_ID}/sampling-configs",
            json={
                "config_name": "列表测试",
                "sampling_type": "statistical",
                "sampling_method": "random",
                "applicable_scenario": "substantive_test",
            },
        )
        resp = await client.get(f"/api/projects/{FAKE_PROJECT_ID}/sampling-configs")
        assert resp.status_code == 200
        data = resp.json()
        items = data.get("data", data)
        assert len(items) >= 1

    @pytest.mark.asyncio
    async def test_update_config_api(self, client, seeded_db):
        # Create
        create_resp = await client.post(
            f"/api/projects/{FAKE_PROJECT_ID}/sampling-configs",
            json={
                "config_name": "待更新",
                "sampling_type": "statistical",
                "sampling_method": "random",
                "applicable_scenario": "substantive_test",
            },
        )
        create_data = create_resp.json()
        config_id = create_data.get("data", create_data)["id"]

        # Update
        resp = await client.put(
            f"/api/projects/{FAKE_PROJECT_ID}/sampling-configs/{config_id}",
            json={"config_name": "已更新"},
        )
        assert resp.status_code == 200
        data = resp.json()
        result = data.get("data", data)
        assert result["config_name"] == "已更新"

    @pytest.mark.asyncio
    async def test_calculate_sample_size_api(self, client, seeded_db):
        resp = await client.post(
            f"/api/projects/{FAKE_PROJECT_ID}/sampling-configs/calculate",
            json={
                "method": "attribute",
                "confidence_level": 0.95,
                "tolerable_deviation_rate": 0.05,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        result = data.get("data", data)
        assert result["calculated_size"] == 60

    @pytest.mark.asyncio
    async def test_calculate_sample_size_api_error(self, client, seeded_db):
        resp = await client.post(
            f"/api/projects/{FAKE_PROJECT_ID}/sampling-configs/calculate",
            json={
                "method": "attribute",
                "tolerable_deviation_rate": 0,
            },
        )
        assert resp.status_code == 400


class TestSamplingRecordAPI:
    """API route tests for sampling record endpoints."""

    @pytest.mark.asyncio
    async def test_create_record_api(self, client, seeded_db):
        resp = await client.post(
            f"/api/projects/{FAKE_PROJECT_ID}/sampling-records",
            json={
                "sampling_purpose": "API测试记录",
                "population_description": "应收账款明细",
                "sample_size": 30,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        result = data.get("data", data)
        assert result["sampling_purpose"] == "API测试记录"
        assert result["sample_size"] == 30

    @pytest.mark.asyncio
    async def test_list_records_api(self, client, seeded_db):
        await client.post(
            f"/api/projects/{FAKE_PROJECT_ID}/sampling-records",
            json={
                "sampling_purpose": "列表测试",
                "population_description": "总体",
                "sample_size": 10,
            },
        )
        resp = await client.get(f"/api/projects/{FAKE_PROJECT_ID}/sampling-records")
        assert resp.status_code == 200
        data = resp.json()
        items = data.get("data", data)
        assert len(items) >= 1

    @pytest.mark.asyncio
    async def test_list_records_filter_wp_api(self, client, seeded_db):
        wp_id = str(seeded_db["wp"].id)
        await client.post(
            f"/api/projects/{FAKE_PROJECT_ID}/sampling-records",
            json={
                "working_paper_id": wp_id,
                "sampling_purpose": "关联底稿",
                "population_description": "总体",
                "sample_size": 10,
            },
        )
        resp = await client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/sampling-records",
            params={"working_paper_id": wp_id},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_record_api(self, client, seeded_db):
        create_resp = await client.post(
            f"/api/projects/{FAKE_PROJECT_ID}/sampling-records",
            json={
                "sampling_purpose": "待更新",
                "population_description": "总体",
                "sample_size": 10,
            },
        )
        create_data = create_resp.json()
        record_id = create_data.get("data", create_data)["id"]

        resp = await client.put(
            f"/api/projects/{FAKE_PROJECT_ID}/sampling-records/{record_id}",
            json={"conclusion": "已完成"},
        )
        assert resp.status_code == 200
        data = resp.json()
        result = data.get("data", data)
        assert result["conclusion"] == "已完成"

    @pytest.mark.asyncio
    async def test_mus_evaluate_api(self, client, seeded_db):
        # Create record with population data
        create_resp = await client.post(
            f"/api/projects/{FAKE_PROJECT_ID}/sampling-records",
            json={
                "sampling_purpose": "MUS评价测试",
                "population_description": "应收账款",
                "population_total_amount": 1000000,
                "sample_size": 50,
            },
        )
        create_data = create_resp.json()
        record_id = create_data.get("data", create_data)["id"]

        resp = await client.post(
            f"/api/projects/{FAKE_PROJECT_ID}/sampling-records/{record_id}/mus-evaluate",
            json={
                "misstatement_details": [
                    {"book_value": 10000, "misstatement_amount": 500},
                ],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        result = data.get("data", data)
        assert "projected_misstatement" in result
        assert "upper_misstatement_limit" in result
        assert result["projected_misstatement"] > 0

    @pytest.mark.asyncio
    async def test_mus_evaluate_api_not_found(self, client, seeded_db):
        fake_id = str(uuid.uuid4())
        resp = await client.post(
            f"/api/projects/{FAKE_PROJECT_ID}/sampling-records/{fake_id}/mus-evaluate",
            json={"misstatement_details": []},
        )
        assert resp.status_code == 400
