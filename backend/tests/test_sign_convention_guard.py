"""符号约定过渡期检测集成测试（真实 PG）。

Task 7.2 / 需求 10：验证 `check_sign_convention_readiness` 在 v1/v2 混存时
正确检测残留并返回 warning，迁移完成后返回 ready，且检测不阻断下游取数。

场景覆盖：
1. 构造 v1+v2 混存数据 → 检测到 v1 残留、返回 warning（has_legacy=True）。
2. 全部标记为 v2 后再检测 → ready=True，无 warning。
3. 检测到 v1 时下游取数（trial_balance router / data_quality router）仍能正常执行
   （不阻断，仅附加 warning）。

PG 不可达则 skip。

Validates: Requirements 10.2, 10.3, 10.4, 10.5
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.audit_platform_models import (
    AccountCategory,
    AccountChart,
    AccountDirection,
    AccountMapping,
    AccountSource,
    MappingType,
    TbBalance,
    TrialBalance,
)
from app.services.ledger_import.sign_convention_guard import (
    SignConventionReadinessResult,
    check_sign_convention_readiness,
)
from app.services.ledger_import.sign_convention_types import (
    CURRENT_SIGN_CONVENTION,
    LEGACY_SIGN_CONVENTION,
)

# 独立测试项目 + 冷门年度
_TEST_PROJECT_ID = uuid.UUID("71900de0-0000-4000-8000-000000007102")
_TEST_YEAR = 2097
_COMPANY = "001"
_V1 = LEGACY_SIGN_CONVENTION
_V2 = CURRENT_SIGN_CONVENTION
_IS_PG = settings.DATABASE_URL.startswith("postgresql")


@pytest_asyncio.fixture
async def pg_factory():
    """真实 PG session factory + 清理 fixture。"""
    if not _IS_PG:
        pytest.skip("need PostgreSQL (sign convention guard integration test)")

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True, echo=False)
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
    except Exception:
        await engine.dispose()
        pytest.skip("PG not reachable")

    factory = async_sessionmaker(engine, expire_on_commit=False)

    from app.models.core import Project, ProjectStatus, ProjectType, User

    async def _cleanup():
        async with factory() as db:
            for tbl in (TrialBalance, TbBalance, AccountMapping, AccountChart):
                await db.execute(
                    sa.delete(tbl).where(tbl.project_id == _TEST_PROJECT_ID)
                )
            # 清理 project（如果存在）
            await db.execute(
                sa.delete(Project).where(Project.id == _TEST_PROJECT_ID)
            )
            await db.commit()

    await _cleanup()

    # seed project + user
    async with factory() as db:
        user = (
            await db.execute(
                sa.select(User).where(User.username == "_guard_test_user")
            )
        ).scalar_one_or_none()
        if user:
            uid = user.id
        else:
            uid = uuid.uuid4()
            db.add(User(
                id=uid, username="_guard_test_user", email="guard@test.com",
                hashed_password="x", role="admin",
            ))
            await db.flush()
        db.add(Project(
            id=_TEST_PROJECT_ID, name="guard-test", client_name="GT",
            project_type=ProjectType.annual, status=ProjectStatus.execution,
            created_by=uid,
        ))
        await db.commit()

    yield factory
    await _cleanup()
    await engine.dispose()


async def _seed_mixed_v1_v2(factory):
    """构造 v1+v2 混存数据：部分科目已迁移到 v2，部分仍为 v1/NULL。"""
    async with factory() as db:
        pid = _TEST_PROJECT_ID
        # 标准科目
        db.add_all([
            AccountChart(
                project_id=pid, account_code="1001", account_name="库存现金",
                direction=AccountDirection.debit, level=1,
                category=AccountCategory.asset, source=AccountSource.standard,
            ),
            AccountChart(
                project_id=pid, account_code="2202", account_name="应付账款",
                direction=AccountDirection.credit, level=1,
                category=AccountCategory.liability, source=AccountSource.standard,
            ),
            AccountChart(
                project_id=pid, account_code="4001", account_name="实收资本",
                direction=AccountDirection.credit, level=1,
                category=AccountCategory.equity, source=AccountSource.standard,
            ),
        ])
        # tb_balance：混存
        db.add_all([
            # 资产：已迁移 v2（正数 + 标 v2）
            TbBalance(
                project_id=pid, year=_TEST_YEAR, company_code=_COMPANY,
                account_code="1001", account_name="库存现金",
                opening_balance=Decimal("80000"), closing_balance=Decimal("100000"),
                debit_amount=Decimal("20000"), credit_amount=Decimal("0"),
                sign_convention_version=_V2,
                closing_direction="debit", opening_direction="debit",
            ),
            # 负债：仍为 v1（负数 + 标 v1）
            TbBalance(
                project_id=pid, year=_TEST_YEAR, company_code=_COMPANY,
                account_code="2202", account_name="应付账款",
                opening_balance=Decimal("-100000"), closing_balance=Decimal("-120000"),
                debit_amount=Decimal("0"), credit_amount=Decimal("20000"),
                sign_convention_version=_V1,
            ),
            # 权益：version=NULL（未迁移，等同 v1）
            TbBalance(
                project_id=pid, year=_TEST_YEAR, company_code=_COMPANY,
                account_code="4001", account_name="实收资本",
                opening_balance=Decimal("-180000"), closing_balance=Decimal("-180000"),
                debit_amount=Decimal("0"), credit_amount=Decimal("0"),
                sign_convention_version=None,
            ),
        ])
        await db.commit()


async def _migrate_all_to_v2(factory):
    """将所有记录标记为 v2（模拟迁移完成）。"""
    async with factory() as db:
        await db.execute(
            sa.update(TbBalance)
            .where(
                TbBalance.project_id == _TEST_PROJECT_ID,
                TbBalance.year == _TEST_YEAR,
            )
            .values(sign_convention_version=_V2)
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Test 1: v1/v2 混存 → 检测到 v1 残留、返回 warning
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detects_v1_residual_in_mixed_data(pg_factory):
    """v1+v2 混存时 check_sign_convention_readiness 检测到 v1 残留、返回 warning。

    Validates: Requirements 10.2, 10.4
    """
    factory = pg_factory
    await _seed_mixed_v1_v2(factory)

    async with factory() as db:
        result = await check_sign_convention_readiness(db, _TEST_PROJECT_ID, _TEST_YEAR)

    assert isinstance(result, SignConventionReadinessResult)
    assert result.ready is False
    assert result.has_legacy is True
    assert result.warning is not None
    assert "符号迁移" in result.warning


# ---------------------------------------------------------------------------
# Test 2: 全部迁移为 v2 后 → ready=True, 无 warning
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_ready_after_full_migration(pg_factory):
    """全部标记为 v2 后检测 → ready=True，无 warning。

    Validates: Requirements 10.5
    """
    factory = pg_factory
    await _seed_mixed_v1_v2(factory)
    await _migrate_all_to_v2(factory)

    async with factory() as db:
        result = await check_sign_convention_readiness(db, _TEST_PROJECT_ID, _TEST_YEAR)

    assert result.ready is True
    assert result.has_legacy is False
    assert result.warning is None


# ---------------------------------------------------------------------------
# Test 3: 检测到 v1 时下游取数仍能正常执行（不阻断，仅 warning）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_downstream_not_blocked_when_v1_detected(pg_factory):
    """检测到 v1 残留时下游 service 仍能正常执行（不阻断，仅 warning）。

    直接调用 service 层验证"检测 + 取数"可组合执行不崩，
    而非通过 ASGI transport（Windows asyncio proactor 有 teardown 竞态）。

    Validates: Requirements 10.3, 10.4
    """
    from app.services.data_quality_service import DataQualityService
    from app.services.trial_balance_service import TrialBalanceService

    factory = pg_factory
    await _seed_mixed_v1_v2(factory)

    async with factory() as db:
        # 1. 检测 v1 残留
        readiness = await check_sign_convention_readiness(db, _TEST_PROJECT_ID, _TEST_YEAR)
        assert readiness.has_legacy is True

        # 2. 下游 service 仍能正常执行（不阻断）
        svc = TrialBalanceService(db)
        rows = await svc.get_trial_balance(_TEST_PROJECT_ID, _TEST_YEAR)
        # 可能无 trial_balance 数据（仅 seed 了 tb_balance），但不应崩
        assert isinstance(rows, list)

        # 3. data_quality 也不崩
        dq = DataQualityService(db)
        result = await dq._check_debit_credit_balance(_TEST_PROJECT_ID, _TEST_YEAR)
        # 即使数据未迁移，校验仍返回结果（不抛异常）
        assert result["status"] in ("passed", "blocking", "warning")


# ---------------------------------------------------------------------------
# Test 4: 空数据（无 tb_balance 行）→ ready=True（无残留）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_data_returns_ready(pg_factory):
    """project+year 无任何 tb_balance 数据时，检测结果为 ready（无残留）。

    Validates: Requirements 10.2
    """
    factory = pg_factory
    # 不 seed 任何 tb_balance 数据

    async with factory() as db:
        result = await check_sign_convention_readiness(db, _TEST_PROJECT_ID, _TEST_YEAR)

    assert result.ready is True
    assert result.has_legacy is False
    assert result.warning is None
