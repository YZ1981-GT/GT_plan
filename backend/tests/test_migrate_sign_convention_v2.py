"""存量数据符号约定迁移脚本集成测试（真实 PG）。

Task 6.5 / 需求 7.1、7.2、7.5、7.7、7.9、8.3：对 Task 6.1-6.4 完成的迁移脚本
`backend/scripts/migrate/migrate_sign_convention_v2.py` 做端到端集成验证（真实 PG）：

- 符号正确（需求 7.1/7.2）：v1 旧约定（借正贷负，负债/权益贷方存负数）数据迁移后，
  贷方类翻为自然正数、补 opening/closing_direction + source、标 sign_convention_version=v2；
  借方类金额不变仅补方向字段；序时账回填 entry_direction。
- dry-run 不写库（需求 7.3）：migrate(dry_run=True) 前后 DB 数据完全不变，仅返回统计。
- 幂等（需求 7.5）：迁移后再跑一次，候选行=0、翻符号行=0，不再翻转。
- 回退（需求 7.9）：rollback_batch 从快照恢复到迁移前 v1 原值（金额、方向、版本全复原）。
- 平衡通过（需求 7.7/8.3）：迁移后重算 trial_balance，借方类合计=贷方类合计
  （data_quality_service._check_debit_credit_balance 判 passed）。

迁移脚本以 `app.core.database.async_session` 直连 settings.DATABASE_URL，与本测试同库；
测试用独立 project_id + 冷门 year，前后清理（含 _sign_migration_backup、app_audit_log）。
PG 不可达则 skip。

Validates: Requirements 7.1, 7.2, 7.5, 7.7, 7.9, 8.3
"""
from __future__ import annotations

import datetime as _dt
import importlib.util
import sys
import uuid
from decimal import Decimal
from pathlib import Path

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
    TbLedger,
    TrialBalance,
)
from app.services.data_quality_service import DataQualityService

# 独立测试项目 + 冷门年度（避免与真实数据/其他测试碰撞）
_TEST_PROJECT_ID = uuid.UUID("519c0de0-0000-4000-8000-0000000061a5")
_TEST_YEAR = 2094
_COMPANY = "001"
_V1 = "v1_net_debit_positive"
_V2 = "v2_category_natural_positive"
_IS_PG = settings.DATABASE_URL.startswith("postgresql")


# ---------------------------------------------------------------------------
# 动态加载迁移脚本模块（位于 backend/scripts/migrate/ 下，非常规包路径）
# ---------------------------------------------------------------------------
_MIG_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts" / "migrate" / "migrate_sign_convention_v2.py"
)
_spec = importlib.util.spec_from_file_location("migrate_sign_convention_v2", _MIG_PATH)
msc = importlib.util.module_from_spec(_spec)
sys.modules["migrate_sign_convention_v2"] = msc  # dataclass 注解解析需模块在 sys.modules
_spec.loader.exec_module(msc)  # type: ignore[union-attr]


@pytest_asyncio.fixture
async def pg_factory():
    """真实 PG session factory + 测试项目 seed + 收尾清理。"""
    if not _IS_PG:
        pytest.skip("need PostgreSQL (sign convention migration integration test)")

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True, echo=False)
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
    except Exception:
        await engine.dispose()
        pytest.skip("PG not reachable")

    factory = async_sessionmaker(engine, expire_on_commit=False)

    # 迁移脚本内部用模块级 async_session（绑定全局 engine，跨事件循环复用会
    # "Event loop is closed"）。指向本测试 per-loop 工厂，保证单一 loop。
    _orig_async_session = msc.async_session
    msc.async_session = factory

    from app.models.core import Project, ProjectStatus, ProjectType, User

    async def _cleanup():
        async with factory() as db:
            for tbl in (TrialBalance, TbLedger, TbBalance, AccountMapping, AccountChart):
                await db.execute(
                    sa.delete(tbl).where(tbl.project_id == _TEST_PROJECT_ID)
                )
            # 迁移快照表 + 审计留痕（表可能尚未建）
            backup_exists = (
                await db.execute(
                    sa.text("SELECT to_regclass('public._sign_migration_backup')")
                )
            ).scalar()
            if backup_exists is not None:
                await db.execute(
                    sa.text(
                        "DELETE FROM _sign_migration_backup WHERE project_id = :p"
                    ),
                    {"p": str(_TEST_PROJECT_ID)},
                )
            audit_exists = (
                await db.execute(
                    sa.text("SELECT to_regclass('public.app_audit_log')")
                )
            ).scalar()
            if audit_exists is not None:
                await db.execute(
                    sa.text(
                        "DELETE FROM app_audit_log "
                        "WHERE resource_id = :rid AND action = 'sign_convention_migrate'"
                    ),
                    {"rid": str(_TEST_PROJECT_ID)},
                )
            await db.commit()

    await _cleanup()

    async with factory() as db:
        user = (
            await db.execute(
                sa.select(User).where(User.username == "_sign_migrate_user")
            )
        ).scalar_one_or_none()
        if user:
            uid = user.id
        else:
            uid = uuid.uuid4()
            db.add(User(
                id=uid, username="_sign_migrate_user", email="signmig@test.com",
                hashed_password="x", role="admin",
            ))
            await db.flush()
        if not (
            await db.execute(sa.select(Project).where(Project.id == _TEST_PROJECT_ID))
        ).scalar_one_or_none():
            db.add(Project(
                id=_TEST_PROJECT_ID, name="sign-migrate-test", client_name="X",
                project_type=ProjectType.annual, status=ProjectStatus.execution,
                created_by=uid,
            ))
        await db.commit()

    yield factory, uid
    await _cleanup()
    msc.async_session = _orig_async_session
    await engine.dispose()


async def _seed_v1(factory, uid):
    """构造一套平衡的 v1 旧约定（借正贷负）账套。

    资产借方存正数；负债/权益贷方存负数（旧约定 closing = 借 - 贷）。
    账套平衡：资产 300000 = 负债 120000 + 权益 180000。
    一条贷方类 version=v1，另一条 version=NULL（覆盖空版本判定路径）。
    """
    async with factory() as db:
        pid = _TEST_PROJECT_ID
        # 标准科目（提供 category，供 trial_balance 重算判类别）
        db.add_all([
            AccountChart(
                project_id=pid, account_code="1001", account_name="库存现金",
                direction=AccountDirection.debit, level=1,
                category=AccountCategory.asset, source=AccountSource.standard,
            ),
            AccountChart(
                project_id=pid, account_code="1122", account_name="应收账款",
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
        # 恒等映射（tb_balance.account_code → 同名标准科目），供 full_recalc 取数
        db.add_all([
            AccountMapping(
                project_id=pid, original_account_code=code,
                original_account_name=name, standard_account_code=code,
                mapping_type=MappingType.auto_exact, created_by=uid,
            )
            for code, name in [
                ("1001", "库存现金"), ("1122", "应收账款"),
                ("2202", "应付账款"), ("4001", "实收资本"),
            ]
        ])
        # tb_balance：v1 旧约定（借正贷负）
        db.add_all([
            # 资产借方正数（借方类，迁移后金额不变）
            TbBalance(
                project_id=pid, year=_TEST_YEAR, company_code=_COMPANY,
                account_code="1001", account_name="库存现金",
                opening_balance=Decimal("80000"), closing_balance=Decimal("100000"),
                debit_amount=Decimal("20000"), credit_amount=Decimal("0"),
                sign_convention_version=_V1,
            ),
            TbBalance(
                project_id=pid, year=_TEST_YEAR, company_code=_COMPANY,
                account_code="1122", account_name="应收账款",
                opening_balance=Decimal("150000"), closing_balance=Decimal("200000"),
                debit_amount=Decimal("50000"), credit_amount=Decimal("0"),
                sign_convention_version=_V1,
            ),
            # 负债贷方余额：v1 存负数（迁移后翻为 +120000）；version=v1
            TbBalance(
                project_id=pid, year=_TEST_YEAR, company_code=_COMPANY,
                account_code="2202", account_name="应付账款",
                opening_balance=Decimal("-100000"), closing_balance=Decimal("-120000"),
                debit_amount=Decimal("0"), credit_amount=Decimal("20000"),
                sign_convention_version=_V1,
            ),
            # 权益贷方余额：v1 存负数（迁移后翻为 +180000）；version=NULL（空版本路径）
            TbBalance(
                project_id=pid, year=_TEST_YEAR, company_code=_COMPANY,
                account_code="4001", account_name="实收资本",
                opening_balance=Decimal("-180000"), closing_balance=Decimal("-180000"),
                debit_amount=Decimal("0"), credit_amount=Decimal("0"),
                sign_convention_version=None,
            ),
        ])
        # tb_ledger：两条分录，借贷分列单边非零（迁移仅回填 entry_direction，金额不翻）
        db.add_all([
            TbLedger(
                project_id=pid, year=_TEST_YEAR, company_code=_COMPANY,
                voucher_date=_dt.date(_TEST_YEAR, 3, 1), voucher_no="V001",
                account_code="1001", account_name="库存现金",
                debit_amount=Decimal("20000"), credit_amount=Decimal("0"),
            ),
            TbLedger(
                project_id=pid, year=_TEST_YEAR, company_code=_COMPANY,
                voucher_date=_dt.date(_TEST_YEAR, 3, 1), voucher_no="V001",
                account_code="2202", account_name="应付账款",
                debit_amount=Decimal("0"), credit_amount=Decimal("20000"),
            ),
        ])
        await db.commit()
    return pid


async def _balance_row(factory, code: str) -> TbBalance:
    async with factory() as db:
        return (
            await db.execute(
                sa.select(TbBalance).where(
                    TbBalance.project_id == _TEST_PROJECT_ID,
                    TbBalance.year == _TEST_YEAR,
                    TbBalance.account_code == code,
                )
            )
        ).scalar_one()


# ---------------------------------------------------------------------------
# dry-run：不写库（需求 7.3）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_does_not_write(pg_factory):
    """dry-run 只统计不写库：迁移前后 DB 数据完全不变。

    Validates: Requirements 7.3
    """
    factory, uid = pg_factory
    pid = await _seed_v1(factory, uid)

    report = await msc.migrate(
        project_id=str(pid), year=_TEST_YEAR, dry_run=True, operator="tester",
    )

    # 报告侧：识别到候选行 + 贷方类待翻符号行（2202 + 4001 = 2 行）
    assert report.dry_run is True
    assert report.total_candidate > 0
    assert report.total_flipped == 2

    # DB 侧：贷方类仍为 v1 负数、版本未变；借方类不变
    liab = await _balance_row(factory, "2202")
    assert liab.closing_balance == Decimal("-120000")
    assert liab.sign_convention_version == _V1
    assert liab.closing_direction is None

    equity = await _balance_row(factory, "4001")
    assert equity.closing_balance == Decimal("-180000")
    assert equity.sign_convention_version is None

    asset = await _balance_row(factory, "1001")
    assert asset.closing_balance == Decimal("100000")
    assert asset.closing_direction is None

    # 序时账 entry_direction 仍为空
    async with factory() as db:
        null_dir = (
            await db.execute(
                sa.select(sa.func.count()).select_from(TbLedger).where(
                    TbLedger.project_id == pid,
                    TbLedger.year == _TEST_YEAR,
                    TbLedger.entry_direction.is_(None),
                )
            )
        ).scalar()
    assert null_dir == 2

    # 快照表不应被创建（dry-run 不建表/不写快照）
    async with factory() as db:
        backup = (
            await db.execute(sa.text("SELECT to_regclass('public._sign_migration_backup')"))
        ).scalar()
        if backup is not None:
            cnt = (
                await db.execute(
                    sa.text("SELECT COUNT(*) FROM _sign_migration_backup WHERE batch_id = :b"),
                    {"b": report.batch_id},
                )
            ).scalar()
            assert cnt == 0


# ---------------------------------------------------------------------------
# 符号正确（需求 7.1、7.2）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_migrate_flips_credit_fills_direction_marks_v2(pg_factory):
    """实际迁移：贷方类翻自然正数+补方向+标 v2；借方类金额不变仅补方向；序时账补 entry_direction。

    Validates: Requirements 7.1, 7.2
    """
    factory, uid = pg_factory
    pid = await _seed_v1(factory, uid)

    report = await msc.migrate(
        project_id=str(pid), year=_TEST_YEAR, dry_run=False, operator="tester",
    )
    assert report.error is None
    assert report.total_flipped == 2

    # 负债贷方：-120000 → +120000，closing_direction=credit，标 v2
    liab = await _balance_row(factory, "2202")
    assert liab.closing_balance == Decimal("120000")
    assert liab.opening_balance == Decimal("100000")
    assert liab.closing_direction == "credit"
    assert liab.opening_direction == "credit"
    assert liab.closing_direction_source
    assert liab.sign_convention_version == _V2

    # 权益贷方（原 version=NULL）：-180000 → +180000
    equity = await _balance_row(factory, "4001")
    assert equity.closing_balance == Decimal("180000")
    assert equity.closing_direction == "credit"
    assert equity.sign_convention_version == _V2

    # 资产借方：金额不变（仍 100000），仅补方向 debit + 标 v2
    asset = await _balance_row(factory, "1001")
    assert asset.closing_balance == Decimal("100000")
    assert asset.opening_balance == Decimal("80000")
    assert asset.closing_direction == "debit"
    assert asset.sign_convention_version == _V2

    # 序时账：entry_direction 已回填（借/贷分列单边非零）
    async with factory() as db:
        ledger_rows = (
            await db.execute(
                sa.select(TbLedger).where(
                    TbLedger.project_id == pid, TbLedger.year == _TEST_YEAR,
                )
            )
        ).scalars().all()
    dir_by_code = {r.account_code: r.entry_direction for r in ledger_rows}
    assert dir_by_code["1001"] == "debit"
    assert dir_by_code["2202"] == "credit"
    assert all(r.entry_direction_source for r in ledger_rows)

    # 审计留痕已写（app_audit_log）
    async with factory() as db:
        audit_exists = (
            await db.execute(sa.text("SELECT to_regclass('public.app_audit_log')"))
        ).scalar()
        if audit_exists is not None:
            audit_cnt = (
                await db.execute(
                    sa.text(
                        "SELECT COUNT(*) FROM app_audit_log "
                        "WHERE resource_id = :rid AND action = 'sign_convention_migrate'"
                    ),
                    {"rid": str(pid)},
                )
            ).scalar()
            assert audit_cnt >= 1


# ---------------------------------------------------------------------------
# 幂等（需求 7.5）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_migrate_idempotent(pg_factory):
    """迁移后再跑：候选行=0、翻符号行=0，不再翻转。

    Validates: Requirements 7.5
    """
    factory, uid = pg_factory
    pid = await _seed_v1(factory, uid)

    # 首次实际迁移
    await msc.migrate(project_id=str(pid), year=_TEST_YEAR, dry_run=False, operator="tester")

    # 再跑（dry-run 即可探测候选）：应无候选、无翻转
    report2 = await msc.migrate(
        project_id=str(pid), year=_TEST_YEAR, dry_run=True, operator="tester",
    )
    assert report2.total_candidate == 0
    assert report2.total_flipped == 0

    # 再跑一次实际迁移：符号不被二次翻转（仍为 +120000）
    await msc.migrate(project_id=str(pid), year=_TEST_YEAR, dry_run=False, operator="tester")
    liab = await _balance_row(factory, "2202")
    assert liab.closing_balance == Decimal("120000")
    assert liab.sign_convention_version == _V2


# ---------------------------------------------------------------------------
# 回退（需求 7.9）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rollback_restores_pre_migration_state(pg_factory):
    """rollback_batch 从快照恢复到迁移前 v1 原值（金额/方向/版本全复原）。

    Validates: Requirements 7.9
    """
    factory, uid = pg_factory
    pid = await _seed_v1(factory, uid)

    report = await msc.migrate(
        project_id=str(pid), year=_TEST_YEAR, dry_run=False, operator="tester",
    )
    # 迁移后确认已翻转
    liab = await _balance_row(factory, "2202")
    assert liab.closing_balance == Decimal("120000")

    # 回退
    async with factory() as db:
        result = await msc.rollback_batch(db, report.batch_id)
    assert result["batch_id"] == report.batch_id
    assert sum(result["restored"].values()) > 0

    # 负债：恢复为 v1 负数 -120000，方向字段/版本复原
    liab = await _balance_row(factory, "2202")
    assert liab.closing_balance == Decimal("-120000")
    assert liab.opening_balance == Decimal("-100000")
    assert liab.closing_direction is None
    assert liab.sign_convention_version == _V1

    # 权益：恢复为 -180000，版本回到 NULL
    equity = await _balance_row(factory, "4001")
    assert equity.closing_balance == Decimal("-180000")
    assert equity.sign_convention_version is None

    # 资产：值未变但方向/版本复原为空
    asset = await _balance_row(factory, "1001")
    assert asset.closing_balance == Decimal("100000")
    assert asset.closing_direction is None
    assert asset.sign_convention_version == _V1

    # 序时账 entry_direction 复原为空
    async with factory() as db:
        null_dir = (
            await db.execute(
                sa.select(sa.func.count()).select_from(TbLedger).where(
                    TbLedger.project_id == pid,
                    TbLedger.year == _TEST_YEAR,
                    TbLedger.entry_direction.is_(None),
                )
            )
        ).scalar()
    assert null_dir == 2


# ---------------------------------------------------------------------------
# 平衡通过（需求 7.7、8.3）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_balance_passes_after_migration(pg_factory):
    """迁移后重算 trial_balance，借方类合计=贷方类合计（data_quality 判 passed）。

    资产 300000（1001 100000 + 1122 200000）= 负债 120000 + 权益 180000。

    Validates: Requirements 7.7, 8.3
    """
    factory, uid = pg_factory
    pid = await _seed_v1(factory, uid)

    report = await msc.migrate(
        project_id=str(pid), year=_TEST_YEAR, dry_run=False, operator="tester",
        recalc_trial_balance=True,
    )
    assert report.error is None
    assert report.trial_balance_recalc is True

    # 迁移 + 重算后跑平衡校验
    async with factory() as db:
        svc = DataQualityService(db)
        result = await svc._check_debit_credit_balance(pid, _TEST_YEAR)

    assert result["status"] == "passed", result
    assert Decimal(result["details"]["debit_total"]) == Decimal("300000")
    assert Decimal(result["details"]["credit_total"]) == Decimal("300000")
    assert Decimal(result["details"]["difference"]) <= Decimal("1")
