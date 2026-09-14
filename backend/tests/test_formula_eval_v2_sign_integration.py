"""公式求值层 v2 符号集成测试（真实 PG）。

Task 5.4 / 需求 11.4、11.5：端到端验证 `=TB()` / `=SUM_TB()` / `=ADJ()` 等公式
从 trial_balance / adjustments 取数时，在 v2 约定（category_natural_positive）下
求值符号正确——尤其负债类（应付账款 2202）预填为符合预期的**正数**。

本测试是端到端集成（非纯函数）：直接 seed v2 自然正数的 trial_balance（资产借方正、
负债贷方正）+ adjustments，再跑真实公式求值器，断言求值结果符号正确。
Task 5.1 已确认求值器代码层无隐式翻转（见 test_formula_tb_sign_passthrough.py），
本任务覆盖"真实取数 → 求值"的完整链路。

## 求值器入口确认（实证）

- 字符串公式 `=TB(...)` / `=SUM_TB(...)` 主路径求值器 =
  `wp_formula_eval_service.evaluate_wp_formula_expression(db, project_id, year, expression)`
  —— 正则 `_TB_PATTERN` / `_SUM_TB_PATTERN`，直接查 `TrialBalance` 表，`_COLUMN_MAP`
  纯列名映射（期末余额→audited_amount），无符号补偿。
- `=ADJ(...)` 求值器 = `wp_cross_check_service.CrossCheckService._eval_expression`
  （同时支持 TB/SUM_TB/ADJ）—— ADJ 查 `adjustment_entries JOIN adjustments`，
  按 `direction_resolver` 将 `SUM(debit-credit)` 归一到科目自然方向（贷方类取反），
  与 trial_balance.aje_adjustment 口径一致。

## 公式语法说明（以求值器实际支持为准）

任务描述用 `=TB_SUM(...)` 与 `=ADJ('1122','aje')`，但代码库求值器实际支持的是：
- 区间求和函数名为 **`SUM_TB`**（非 `TB_SUM`），见 `_SUM_TB_PATTERN`。
- ADJ 类型参数为 **`aje_net`/`rje_net`**（非 `aje`/`rje`），见 `_get_adj_value`。
本测试以求值器实际语法为准（`SUM_TB` / `aje_net`），保证测试真实可运行。

## ADJ 符号口径说明（已统一，2026-06-08 复盘修复）

`CrossCheckService._get_adj_value` 已按 `direction_resolver` 将原始 `SUM(debit-credit)`
归一到科目自然方向（借方类 sign=+1、贷方类 sign=-1），与 Task 3.3
`recalc_adjustments` 写 `trial_balance.aje_adjustment/rje_adjustment` 同口径。
故 `ADJ('1122','aje_net')`（资产借记）与 `ADJ('2202','aje_net')`（负债贷记增加）
均返回正数，与审定数推导 `audited=unadjusted+aje+rje` 一致，不再有口径差异。

需真实 PG（与 test_trial_balance_sign_passthrough.py 同款 fixture），PG 不可达则 skip。

Validates: Requirements 11.4, 11.5
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
    Adjustment,
    AdjustmentEntry,
    AdjustmentType,
    ReviewStatus,
    TrialBalance,
)
from app.services.wp_cross_check_service import CrossCheckService
from app.services.wp_formula_eval_service import evaluate_wp_formula_expression

_TEST_PROJECT_ID = uuid.UUID("519c0de0-0000-4000-8000-00000000f504")
_TEST_YEAR = 2095
_COMPANY = "001"
_IS_PG = settings.DATABASE_URL.startswith("postgresql")


@pytest_asyncio.fixture
async def pg_factory():
    """真实 PG session factory + 测试项目 seed + 收尾清理。"""
    if not _IS_PG:
        pytest.skip("need PostgreSQL (formula eval v2 sign integration test)")

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
            # 先删明细行（FK 指向 adjustments），再删头表与 trial_balance
            adj_ids = (
                await db.execute(
                    sa.select(Adjustment.id).where(
                        Adjustment.project_id == _TEST_PROJECT_ID
                    )
                )
            ).scalars().all()
            if adj_ids:
                await db.execute(
                    sa.delete(AdjustmentEntry).where(
                        AdjustmentEntry.adjustment_id.in_(adj_ids)
                    )
                )
            await db.execute(
                sa.delete(Adjustment).where(Adjustment.project_id == _TEST_PROJECT_ID)
            )
            await db.execute(
                sa.delete(TrialBalance).where(
                    TrialBalance.project_id == _TEST_PROJECT_ID
                )
            )
            await db.commit()

    await _cleanup()

    async with factory() as db:
        user = (
            await db.execute(
                sa.select(User).where(User.username == "_formula_eval_v2_user")
            )
        ).scalar_one_or_none()
        if user:
            uid = user.id
        else:
            uid = uuid.uuid4()
            db.add(
                User(
                    id=uid,
                    username="_formula_eval_v2_user",
                    email="formulaevalv2@test.com",
                    hashed_password="x",
                    role="admin",
                )
            )
            await db.flush()
        if not (
            await db.execute(
                sa.select(Project).where(Project.id == _TEST_PROJECT_ID)
            )
        ).scalar_one_or_none():
            db.add(
                Project(
                    id=_TEST_PROJECT_ID,
                    name="formula-eval-v2-test",
                    client_name="X",
                    project_type=ProjectType.annual,
                    status=ProjectStatus.execution,
                    created_by=uid,
                )
            )
        await db.commit()

    yield factory, uid
    await _cleanup()
    await engine.dispose()


def _tb(
    code: str,
    name: str,
    category: AccountCategory,
    *,
    audited: Decimal,
    unadjusted: Decimal | None = None,
    opening: Decimal | None = None,
) -> TrialBalance:
    """构造一条 v2 自然正数的 trial_balance 行。"""
    return TrialBalance(
        project_id=_TEST_PROJECT_ID,
        year=_TEST_YEAR,
        company_code=_COMPANY,
        standard_account_code=code,
        account_name=name,
        account_category=category,
        unadjusted_amount=unadjusted if unadjusted is not None else audited,
        audited_amount=audited,
        opening_balance=opening if opening is not None else Decimal("0"),
    )


async def _seed_tb(factory) -> None:
    """seed v2 自然正数试算表：资产借方正、负债贷方正。"""
    async with factory() as db:
        await db.execute(
            sa.delete(TrialBalance).where(
                TrialBalance.project_id == _TEST_PROJECT_ID
            )
        )
        db.add_all([
            # 资产借方正数
            _tb("1121", "交易性金融资产", AccountCategory.asset,
                audited=Decimal("30000"), opening=Decimal("25000")),
            _tb("1122", "应收账款", AccountCategory.asset,
                audited=Decimal("50000"), opening=Decimal("40000")),
            # 负债贷方正常 → v2 存正数（关键断言：预填为正数，非旧约定负数）
            _tb("2202", "应付账款", AccountCategory.liability,
                audited=Decimal("8000"), opening=Decimal("6000")),
        ])
        await db.commit()


async def _seed_aje(factory, uid, code: str, name: str,
                    *, debit: Decimal, credit: Decimal) -> None:
    """seed 一笔 AJE 调整（头表 + 明细行），供 ADJ('code','aje_net') 求值。"""
    async with factory() as db:
        group_id = uuid.uuid4()
        adj = Adjustment(
            project_id=_TEST_PROJECT_ID,
            year=_TEST_YEAR,
            company_code=_COMPANY,
            adjustment_no=f"AJE-{code}",
            adjustment_type=AdjustmentType.aje,
            account_code=code,
            account_name=name,
            debit_amount=debit,
            credit_amount=credit,
            entry_group_id=group_id,
            review_status=ReviewStatus.approved,
            created_by=uid,
        )
        db.add(adj)
        await db.flush()
        db.add(AdjustmentEntry(
            adjustment_id=adj.id,
            entry_group_id=group_id,
            line_no=1,
            standard_account_code=code,
            account_name=name,
            debit_amount=debit,
            credit_amount=credit,
        ))
        await db.commit()


# ─────────────────────────────────────────────────────────────────────────
# 需求 11.4：典型公式 =TB('2202','期末余额')（负债类）预填为正数
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tb_liability_closing_is_positive(pg_factory):
    """`=TB('2202','期末余额')`（应付账款，负债类）在 v2 下预填为正数 8000。

    这是需求 11.4 的核心断言：负债类 TB 取数不被翻成负数。

    Validates: Requirements 11.4
    """
    factory, _uid = pg_factory
    await _seed_tb(factory)

    async with factory() as db:
        value, errors = await evaluate_wp_formula_expression(
            db,
            project_id=_TEST_PROJECT_ID,
            year=_TEST_YEAR,
            expression="=TB('2202','期末余额')",
        )

    assert errors == [], errors
    assert value == Decimal("8000")
    assert value > 0, "负债类期末余额在 v2 下必须为正数"


@pytest.mark.asyncio
async def test_tb_asset_closing_is_positive(pg_factory):
    """`=TB('1122','期末余额')`（应收账款，资产类）预填为正数 50000。

    Validates: Requirements 11.5
    """
    factory, _uid = pg_factory
    await _seed_tb(factory)

    async with factory() as db:
        value, errors = await evaluate_wp_formula_expression(
            db,
            project_id=_TEST_PROJECT_ID,
            year=_TEST_YEAR,
            expression="=TB('1122','期末余额')",
        )

    assert errors == [], errors
    assert value == Decimal("50000")
    assert value > 0


@pytest.mark.asyncio
async def test_tb_opening_column_positive(pg_factory):
    """`=TB('2202','年初余额')` 取 opening_balance 列，负债类年初亦为正数 6000。

    验证列名映射（年初余额→opening_balance）在 v2 下无翻转。

    Validates: Requirements 11.5
    """
    factory, _uid = pg_factory
    await _seed_tb(factory)

    async with factory() as db:
        value, errors = await evaluate_wp_formula_expression(
            db,
            project_id=_TEST_PROJECT_ID,
            year=_TEST_YEAR,
            expression="=TB('2202','年初余额')",
        )

    assert errors == [], errors
    assert value == Decimal("6000")
    assert value > 0


# ─────────────────────────────────────────────────────────────────────────
# 需求 11.5：SUM_TB 区间合计求值符号正确
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sum_tb_range_total_positive(pg_factory):
    """`=SUM_TB('1121~1122','期末余额')` 区间合计 = 30000 + 50000 = 80000（正数）。

    任务描述写 `=TB_SUM(...)`，求值器实际函数名为 `SUM_TB`，以实际为准。

    Validates: Requirements 11.5
    """
    factory, _uid = pg_factory
    await _seed_tb(factory)

    async with factory() as db:
        value, errors = await evaluate_wp_formula_expression(
            db,
            project_id=_TEST_PROJECT_ID,
            year=_TEST_YEAR,
            expression="=SUM_TB('1121~1122','期末余额')",
        )

    assert errors == [], errors
    assert value == Decimal("80000")
    assert value > 0


@pytest.mark.asyncio
async def test_arithmetic_expression_preserves_signs(pg_factory):
    """复合算术 `=TB('1122','期末余额')-TB('2202','期末余额')` = 50000 - 8000 = 42000。

    验证多 TB 取数在四则运算下符号与数值均正确传递（资产 − 负债，均为 v2 正数）。

    Validates: Requirements 11.5
    """
    factory, _uid = pg_factory
    await _seed_tb(factory)

    async with factory() as db:
        value, errors = await evaluate_wp_formula_expression(
            db,
            project_id=_TEST_PROJECT_ID,
            year=_TEST_YEAR,
            expression="=TB('1122','期末余额')-TB('2202','期末余额')",
        )

    assert errors == [], errors
    assert value == Decimal("42000")


# ─────────────────────────────────────────────────────────────────────────
# 需求 11.5：ADJ 公式求值符号正确（CrossCheckService 路径）
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_adj_debit_account_positive(pg_factory):
    """`ADJ('1122','aje_net')`（应收账款借记调整）求值为正数 +500。

    借方正常类科目一笔借记调整（debit 500）使其增大 → SUM(debit-credit)=+500，
    与 Task 3.3 recalc_adjustments 归一口径（借方类 sign=+1）一致。

    Validates: Requirements 11.5
    """
    factory, uid = pg_factory
    await _seed_tb(factory)
    await _seed_aje(factory, uid, "1122", "应收账款",
                    debit=Decimal("500"), credit=Decimal("0"))

    async with factory() as db:
        svc = CrossCheckService(db)
        value = await svc._eval_expression(
            _TEST_PROJECT_ID, _TEST_YEAR, "ADJ('1122','aje_net')"
        )

    assert value == Decimal("500")
    assert value > 0


@pytest.mark.asyncio
async def test_adj_credit_account_normalized_positive(pg_factory):
    """`ADJ('2202','aje_net')`（应付账款贷记增加）经方向归一后求值为正数 +1000。

    v2 修复（口径统一）：负债类一笔贷记调整（credit 1000，负债增加）原始
    SUM(debit-credit)=-1000，但 _get_adj_value 已按 direction_resolver 归一
    （贷方类取反），返回 +1000，与 trial_balance.aje_adjustment（Task 3.3 归一）
    及审定数推导 audited=unadjusted+aje 口径一致。

    Validates: Requirements 11.5, 6.7
    """
    factory, uid = pg_factory
    await _seed_tb(factory)
    await _seed_aje(factory, uid, "2202", "应付账款",
                    debit=Decimal("0"), credit=Decimal("1000"))

    async with factory() as db:
        svc = CrossCheckService(db)
        value = await svc._eval_expression(
            _TEST_PROJECT_ID, _TEST_YEAR, "ADJ('2202','aje_net')"
        )

    # 贷方类归一为 +1000（非旧实现的原始净额 -1000）
    assert value == Decimal("1000")
    assert value > 0


@pytest.mark.asyncio
async def test_adj_no_entry_returns_zero(pg_factory):
    """无调整分录时 `ADJ('2202','aje_net')` 求值为 0（不抛错、不产生伪符号）。

    Validates: Requirements 11.5
    """
    factory, _uid = pg_factory
    await _seed_tb(factory)

    async with factory() as db:
        svc = CrossCheckService(db)
        value = await svc._eval_expression(
            _TEST_PROJECT_ID, _TEST_YEAR, "ADJ('2202','aje_net')"
        )

    assert value == Decimal("0")


@pytest.mark.asyncio
async def test_cross_check_tb_matches_formula_eval(pg_factory):
    """两套求值器对同一 `TB('2202','期末余额')` 取数符号/数值一致（均 v2 正数 8000）。

    交叉验证 wp_formula_eval_service 与 wp_cross_check_service 两条求值路径
    在 v2 约定下口径统一，负债类均返回正数，无任一路径隐式翻转。

    Validates: Requirements 11.4, 11.5
    """
    factory, _uid = pg_factory
    await _seed_tb(factory)

    async with factory() as db:
        wp_value, errors = await evaluate_wp_formula_expression(
            db,
            project_id=_TEST_PROJECT_ID,
            year=_TEST_YEAR,
            expression="=TB('2202','期末余额')",
        )
        svc = CrossCheckService(db)
        cc_value = await svc._eval_expression(
            _TEST_PROJECT_ID, _TEST_YEAR, "TB('2202','期末余额')"
        )

    assert errors == [], errors
    assert wp_value == Decimal("8000")
    assert cc_value == Decimal("8000")
    assert wp_value == cc_value
