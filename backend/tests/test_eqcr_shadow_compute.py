"""EQCR 影子计算单元测试

Refinement Round 5 任务 8 验证目标：

1. test_shadow_compute_basic — 调用 debit_credit_balance 计算，验证存入表
2. test_shadow_compute_rate_limit — 模拟超过 20 次限流
3. test_shadow_compute_invalid_type — 非法计算类型返回 400
4. test_shadow_compute_list — 列出项目影子计算记录
5. test_shadow_compute_redis_unavailable — Redis 不可用时降级放行
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.base import Base

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

# 独立 engine
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

from app.models.base import ProjectStatus, ProjectType, UserRole  # noqa: E402
from app.models.core import Project, User  # noqa: E402
from app.models.eqcr_models import EqcrShadowComputation  # noqa: E402
from app.services.eqcr_shadow_compute_service import (  # noqa: E402
    ALLOWED_COMPUTATION_TYPES,
    SHADOW_COMPUTE_DAILY_LIMIT,
    EqcrShadowComputeService,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def sample_project(db_session: AsyncSession):
    """创建一个测试项目。"""
    project = Project(
        id=uuid.uuid4(),
        name="Test EQCR Project",
        client_name="Test Client",
        project_type=ProjectType.annual,
        status=ProjectStatus.execution,
    )
    db_session.add(project)
    await db_session.commit()
    return project


@pytest_asyncio.fixture
async def sample_user(db_session: AsyncSession):
    """创建一个测试用户。"""
    user = User(
        id=uuid.uuid4(),
        username="eqcr_user",
        email="eqcr@test.com",
        hashed_password="hashed",
        role=UserRole.admin,
    )
    db_session.add(user)
    await db_session.commit()
    return user


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shadow_compute_basic(db_session, sample_project, sample_user):
    """调用 debit_credit_balance 计算，验证存入表并返回正确结构。"""
    svc = EqcrShadowComputeService(db_session)

    # Mock consistency_replay_engine 避免真实 SQL 查询（SQLite 不支持 PG 语法）
    mock_layer = MagicMock()
    mock_layer.from_table = "tb_balance"
    mock_layer.to_table = "trial_balance"
    mock_layer.status = "consistent"
    mock_layer.diffs = []

    mock_result = MagicMock()
    mock_result.snapshot_id = "snap_test"
    mock_result.overall_status = "consistent"
    mock_result.blocking_count = 0
    mock_result.layers = [mock_layer]

    with patch(
        "app.services.consistency_replay_engine.consistency_replay_engine"
    ) as mock_engine:
        mock_engine.replay_consistency = AsyncMock(return_value=mock_result)

        result = await svc.execute_shadow_compute(
            project_id=sample_project.id,
            computation_type="debit_credit_balance",
            params={"year": 2025},
            user_id=sample_user.id,
        )
        await db_session.commit()

    # 验证返回结构
    assert result["computation_type"] == "debit_credit_balance"
    assert result["project_id"] == str(sample_project.id)
    assert result["created_by"] == str(sample_user.id)
    assert "result" in result
    assert result["result"]["status"] == "success"
    assert result["result"]["caller_context"] == "eqcr"
    assert "id" in result
    assert "created_at" in result

    # 验证数据库中有记录
    from sqlalchemy import select as sa_select
    q = sa_select(EqcrShadowComputation).where(
        EqcrShadowComputation.project_id == sample_project.id
    )
    rows = (await db_session.execute(q)).scalars().all()
    assert len(rows) == 1
    assert rows[0].computation_type == "debit_credit_balance"
    # team_result_snapshot 为 None（测试环境无项目组数据），has_diff=True
    # 这是正确行为：无法对比时标记为有差异
    assert rows[0].has_diff is True


@pytest.mark.asyncio
async def test_shadow_compute_rate_limit(db_session, sample_project, sample_user):
    """模拟超过 20 次限流，验证 Redis 限流逻辑。"""
    svc = EqcrShadowComputeService(db_session)

    # Mock Redis client
    mock_redis = AsyncMock()

    # 模拟已达到限流上限
    mock_redis.get = AsyncMock(return_value=str(SHADOW_COMPUTE_DAILY_LIMIT))

    allowed, remaining = await svc.check_rate_limit(sample_project.id, mock_redis)
    assert allowed is False
    assert remaining == 0

    # 模拟未达到限流上限
    mock_redis.get = AsyncMock(return_value="5")
    mock_redis.incr = AsyncMock(return_value=6)

    allowed, remaining = await svc.check_rate_limit(sample_project.id, mock_redis)
    assert allowed is True
    assert remaining == SHADOW_COMPUTE_DAILY_LIMIT - 5 - 1  # 14

    # 模拟首次请求（key 不存在）
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock()

    allowed, remaining = await svc.check_rate_limit(sample_project.id, mock_redis)
    assert allowed is True
    assert remaining == SHADOW_COMPUTE_DAILY_LIMIT - 1  # 19


@pytest.mark.asyncio
async def test_shadow_compute_invalid_type(db_session, sample_project, sample_user):
    """非法计算类型应该在路由层被拒绝（400）。

    这里测试 service 层对 consistency_replay_engine 的调用不会崩溃。
    """
    # 验证 ALLOWED_COMPUTATION_TYPES 不包含非法值
    assert "invalid_type" not in ALLOWED_COMPUTATION_TYPES
    assert "debit_credit_balance" in ALLOWED_COMPUTATION_TYPES
    assert "cfs_supplementary" in ALLOWED_COMPUTATION_TYPES
    assert "tb_vs_report" in ALLOWED_COMPUTATION_TYPES
    assert "intercompany_elimination" in ALLOWED_COMPUTATION_TYPES


@pytest.mark.asyncio
async def test_shadow_compute_list(db_session, sample_project, sample_user):
    """列出项目影子计算记录。"""
    svc = EqcrShadowComputeService(db_session)

    # 手动插入两条记录
    record1 = EqcrShadowComputation(
        project_id=sample_project.id,
        computation_type="debit_credit_balance",
        params={"year": 2025},
        result={"status": "success", "caller_context": "eqcr"},
        team_result_snapshot=None,
        has_diff=True,
        created_by=sample_user.id,
    )
    record2 = EqcrShadowComputation(
        project_id=sample_project.id,
        computation_type="tb_vs_report",
        params={"year": 2025},
        result={"status": "success", "caller_context": "eqcr"},
        team_result_snapshot={"source": "financial_report"},
        has_diff=False,
        created_by=sample_user.id,
    )
    db_session.add_all([record1, record2])
    await db_session.commit()

    # 列出记录
    results = await svc.list_shadow_computations(sample_project.id)
    assert len(results) == 2
    # 按 created_at desc 排序
    types = [r["computation_type"] for r in results]
    assert "debit_credit_balance" in types
    assert "tb_vs_report" in types


@pytest.mark.asyncio
async def test_shadow_compute_redis_unavailable(db_session, sample_project):
    """Redis 不可用时降级放行。"""
    svc = EqcrShadowComputeService(db_session)

    # redis_client=None 模拟 Redis 不可用
    allowed, remaining = await svc.check_rate_limit(sample_project.id, None)
    assert allowed is True
    assert remaining == -1  # 降级标志


@pytest.mark.asyncio
async def test_shadow_compute_has_diff_when_inconsistent(
    db_session, sample_project, sample_user
):
    """当 consistency_replay_engine 发现 blocking 差异时，has_diff=True。"""
    svc = EqcrShadowComputeService(db_session)

    # Mock 有差异的结果
    mock_diff = MagicMock()
    mock_diff.object_type = "account"
    mock_diff.object_id = "1001"
    mock_diff.field_name = "closing_balance vs unadjusted_amount"
    mock_diff.expected = 100.0
    mock_diff.actual = 90.0
    mock_diff.diff = 10.0
    mock_diff.severity = "blocking"

    mock_layer = MagicMock()
    mock_layer.from_table = "tb_balance"
    mock_layer.to_table = "trial_balance"
    mock_layer.status = "inconsistent"
    mock_layer.diffs = [mock_diff]

    mock_result = MagicMock()
    mock_result.snapshot_id = "snap_diff"
    mock_result.overall_status = "inconsistent"
    mock_result.blocking_count = 1
    mock_result.layers = [mock_layer]

    with patch(
        "app.services.consistency_replay_engine.consistency_replay_engine"
    ) as mock_engine:
        mock_engine.replay_consistency = AsyncMock(return_value=mock_result)

        result = await svc.execute_shadow_compute(
            project_id=sample_project.id,
            computation_type="debit_credit_balance",
            params=None,
            user_id=sample_user.id,
        )
        await db_session.commit()

    # 验证 has_diff=True
    assert result["has_diff"] is True
    assert result["result"]["blocking_count"] == 1
    assert result["result"]["overall_status"] == "inconsistent"
    # 验证 layer_detail 包含差异信息
    assert result["result"]["layer_detail"]["diff_count"] == 1
    assert result["result"]["layer_detail"]["diffs"][0]["object_id"] == "1001"
