"""QC 规则试运行（dry-run）服务单元测试

Validates: Requirements 2 (Round 3)
- 对采样底稿跑规则沙箱，不写 DB，返回命中率
- scope='project' 限定项目范围
- scope='all' 全部项目
- sample_size 控制采样大小
- 异步判断逻辑（sample_size > 100 走异步）
- 结果不写入 wp_qc_results
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.qc_rule_models import QcRuleDefinition
from app.models.workpaper_models import WorkingPaper, WpIndex

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
        yield session


def _create_rule(
    rule_code: str = "QC-DRY-01",
    expression_type: str = "jsonpath",
    expression: str = "$.conclusion",
    severity: str = "warning",
    scope: str = "workpaper",
    **kwargs,
) -> QcRuleDefinition:
    """创建测试用规则对象。"""
    return QcRuleDefinition(
        id=kwargs.get("id", uuid.uuid4()),
        rule_code=rule_code,
        severity=severity,
        scope=scope,
        category="测试",
        title="测试规则",
        description="测试用",
        expression_type=expression_type,
        expression=expression,
        enabled=True,
        version=1,
        created_by=uuid.uuid4(),
    )


async def _seed_workpapers(
    db: AsyncSession,
    project_id: uuid.UUID,
    count: int = 5,
    parsed_data_factory=None,
) -> list[uuid.UUID]:
    """向数据库插入测试底稿，返回 wp_id 列表。"""
    wp_ids = []
    for i in range(count):
        wp_index_id = uuid.uuid4()
        wp_id = uuid.uuid4()

        # 创建 WpIndex
        wp_index = WpIndex(
            id=wp_index_id,
            project_id=project_id,
            wp_code=f"D-{i+1:03d}",
            wp_name=f"测试底稿 {i+1}",
            audit_cycle="D",
            status="in_progress",
        )
        db.add(wp_index)

        # 创建 WorkingPaper
        parsed_data = (
            parsed_data_factory(i) if parsed_data_factory else {"conclusion": f"结论{i}"}
        )
        wp = WorkingPaper(
            id=wp_id,
            project_id=project_id,
            wp_index_id=wp_index_id,
            file_path=f"/test/wp_{i}.xlsx",
            source_type="template",
            status="draft",
            review_status="not_submitted",
            parsed_data=parsed_data,
        )
        db.add(wp)
        wp_ids.append(wp_id)

    await db.flush()
    return wp_ids


# ═══ DRY-RUN SERVICE TESTS ═══════════════════════════════════════


class TestDryRunService:
    """QcRuleDryRunService 单元测试"""

    @pytest.mark.asyncio
    async def test_dry_run_no_workpapers_returns_zero(self, db_session: AsyncSession):
        """无底稿时返回 total_checked=0, hits=0。"""
        from app.services.qc_rule_dry_run_service import qc_rule_dry_run_service

        rule = _create_rule(expression="$.conclusion")
        db_session.add(rule)
        await db_session.flush()

        result = await qc_rule_dry_run_service.run_dry_run(
            db_session, rule, scope="all"
        )

        assert result.total_checked == 0
        assert result.hits == 0
        assert result.hit_rate == 0.0
        assert result.sample_findings == []

    @pytest.mark.asyncio
    async def test_dry_run_jsonpath_hits(self, db_session: AsyncSession):
        """JSONPath 规则命中：expect_match=True 但 parsed_data 无匹配字段。"""
        from app.services.qc_rule_dry_run_service import qc_rule_dry_run_service

        # 规则期望 $.nonexistent 存在（expect_match=True 默认）
        rule = _create_rule(
            expression="$.nonexistent_field",
            expression_type="jsonpath",
        )
        db_session.add(rule)

        project_id = uuid.uuid4()
        await _seed_workpapers(
            db_session,
            project_id,
            count=3,
            parsed_data_factory=lambda i: {"conclusion": f"结论{i}"},
        )

        result = await qc_rule_dry_run_service.run_dry_run(
            db_session, rule, scope="all", sample_size=10
        )

        # 所有底稿都不含 nonexistent_field，全部命中
        assert result.total_checked == 3
        assert result.hits == 3
        assert result.hit_rate == 1.0
        assert len(result.sample_findings) > 0

    @pytest.mark.asyncio
    async def test_dry_run_jsonpath_passes(self, db_session: AsyncSession):
        """JSONPath 规则通过：expect_match=True 且 parsed_data 有匹配字段。"""
        from app.services.qc_rule_dry_run_service import qc_rule_dry_run_service

        # 规则期望 $.conclusion 存在
        rule = _create_rule(
            expression="$.conclusion",
            expression_type="jsonpath",
        )
        db_session.add(rule)

        project_id = uuid.uuid4()
        await _seed_workpapers(
            db_session,
            project_id,
            count=3,
            parsed_data_factory=lambda i: {"conclusion": f"结论{i}"},
        )

        result = await qc_rule_dry_run_service.run_dry_run(
            db_session, rule, scope="all", sample_size=10
        )

        # 所有底稿都有 conclusion 字段，全部通过
        assert result.total_checked == 3
        assert result.hits == 0
        assert result.hit_rate == 0.0

    @pytest.mark.asyncio
    async def test_dry_run_scope_project_filters(self, db_session: AsyncSession):
        """scope='project' 只查指定项目的底稿。"""
        from app.services.qc_rule_dry_run_service import qc_rule_dry_run_service

        rule = _create_rule(expression="$.nonexistent")
        db_session.add(rule)

        project_a = uuid.uuid4()
        project_b = uuid.uuid4()
        await _seed_workpapers(db_session, project_a, count=3)
        await _seed_workpapers(db_session, project_b, count=5)

        # 只查 project_a
        result = await qc_rule_dry_run_service.run_dry_run(
            db_session,
            rule,
            scope="project",
            project_ids=[project_a],
            sample_size=50,
        )

        assert result.total_checked == 3

    @pytest.mark.asyncio
    async def test_dry_run_sample_size_limits(self, db_session: AsyncSession):
        """sample_size 限制返回数量。"""
        from app.services.qc_rule_dry_run_service import qc_rule_dry_run_service

        rule = _create_rule(expression="$.nonexistent")
        db_session.add(rule)

        project_id = uuid.uuid4()
        await _seed_workpapers(db_session, project_id, count=10)

        result = await qc_rule_dry_run_service.run_dry_run(
            db_session, rule, scope="all", sample_size=3
        )

        assert result.total_checked == 3

    @pytest.mark.asyncio
    async def test_dry_run_does_not_write_to_qc_results(self, db_session: AsyncSession):
        """dry-run 不写入 wp_qc_results 表。"""
        from sqlalchemy import select

        from app.models.workpaper_models import WpQcResult
        from app.services.qc_rule_dry_run_service import qc_rule_dry_run_service

        rule = _create_rule(expression="$.nonexistent")
        db_session.add(rule)

        project_id = uuid.uuid4()
        await _seed_workpapers(db_session, project_id, count=3)

        await qc_rule_dry_run_service.run_dry_run(
            db_session, rule, scope="all", sample_size=10
        )

        # 验证 wp_qc_results 表无新记录
        qc_results = (
            await db_session.execute(select(WpQcResult))
        ).scalars().all()
        assert len(qc_results) == 0

    @pytest.mark.asyncio
    async def test_dry_run_result_structure(self, db_session: AsyncSession):
        """验证返回结构包含 total_checked, hits, hit_rate, sample_findings。"""
        from app.services.qc_rule_dry_run_service import qc_rule_dry_run_service

        rule = _create_rule(expression="$.nonexistent")
        db_session.add(rule)

        project_id = uuid.uuid4()
        await _seed_workpapers(db_session, project_id, count=2)

        result = await qc_rule_dry_run_service.run_dry_run(
            db_session, rule, scope="all"
        )

        result_dict = result.to_dict()
        assert "total_checked" in result_dict
        assert "hits" in result_dict
        assert "hit_rate" in result_dict
        assert "sample_findings" in result_dict
        assert isinstance(result_dict["sample_findings"], list)

        # 验证 finding 结构
        if result_dict["sample_findings"]:
            finding = result_dict["sample_findings"][0]
            assert "wp_id" in finding
            assert "wp_code" in finding
            assert "message" in finding
            assert "severity" in finding


class TestDryRunAsyncDecision:
    """异步判断逻辑"""

    @pytest.mark.asyncio
    async def test_should_run_async_small_sample(self, db_session: AsyncSession):
        """sample_size <= 100 走同步。"""
        from app.services.qc_rule_dry_run_service import qc_rule_dry_run_service

        rule = _create_rule()
        result = await qc_rule_dry_run_service.should_run_async(
            db_session, rule, "all", sample_size=50
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_should_run_async_large_sample(self, db_session: AsyncSession):
        """sample_size > 100 走异步。"""
        from app.services.qc_rule_dry_run_service import qc_rule_dry_run_service

        rule = _create_rule()
        result = await qc_rule_dry_run_service.should_run_async(
            db_session, rule, "all", sample_size=200
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_should_run_async_default_sample(self, db_session: AsyncSession):
        """默认 sample_size=50 走同步。"""
        from app.services.qc_rule_dry_run_service import qc_rule_dry_run_service

        rule = _create_rule()
        result = await qc_rule_dry_run_service.should_run_async(
            db_session, rule, "all", sample_size=None
        )
        assert result is False


class TestDryRunMixedResults:
    """混合命中/通过场景"""

    @pytest.mark.asyncio
    async def test_partial_hits(self, db_session: AsyncSession):
        """部分底稿命中、部分通过。"""
        from app.services.qc_rule_dry_run_service import qc_rule_dry_run_service

        # 规则期望 $.conclusion 存在
        rule = _create_rule(expression="$.conclusion")
        db_session.add(rule)

        project_id = uuid.uuid4()
        # 3 张有 conclusion，2 张没有
        await _seed_workpapers(
            db_session,
            project_id,
            count=5,
            parsed_data_factory=lambda i: (
                {"conclusion": f"结论{i}"} if i < 3 else {"other_field": "value"}
            ),
        )

        result = await qc_rule_dry_run_service.run_dry_run(
            db_session, rule, scope="all", sample_size=50
        )

        assert result.total_checked == 5
        assert result.hits == 2  # 2 张没有 conclusion
        assert 0 < result.hit_rate < 1.0
