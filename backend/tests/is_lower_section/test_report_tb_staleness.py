"""试算表陈旧口径提示（spec income-statement-lower-section-formulas，ADR-ISL-05）。

两项检查分层验证：

- 贷方性质损益科目为负：真 ORM（SQLite，``tests/formula_settings/_env``）逐行落库后现查；
- 余额表 v1 残留：``check_sign_convention_readiness`` 用 PG 专有的 ``to_regclass`` 探表，SQLite 上跑不了 ⇒
  故障注在**被测函数的下一层**（替换该函数，不替换 ``stale_trial_balance_warning`` 自身），验证组合逻辑；
  真库形态由 ``test_report_tb_staleness_pg.py`` 的 pg_only 用例覆盖。
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from decimal import Decimal

import pytest

from app.models.audit_platform_models import TrialBalance
from app.services.report_tb_staleness import (
    STALE_WARNING,
    negative_credit_pl_accounts,
    stale_trial_balance_warning,
)
from tests.formula_settings._env import make_db

YEAR = 2025
GUARD_MODULE = "app.services.ledger_import.sign_convention_guard"


@dataclass
class _Readiness:
    """``SignConventionReadinessResult`` 的最小替身（只用到这两个字段）。"""

    ready: bool
    has_legacy: bool
    warning: str | None = None


@pytest.fixture
def no_legacy(monkeypatch):
    """下一层：余额表没有 v1 残留。"""
    import app.services.ledger_import.sign_convention_guard as guard

    async def _check(db, project_id, year):  # noqa: ANN001, ARG001
        return _Readiness(ready=True, has_legacy=False)

    monkeypatch.setattr(guard, "check_sign_convention_readiness", _check)


@pytest.fixture
def has_legacy(monkeypatch):
    """下一层：余额表含 v1 残留。"""
    import app.services.ledger_import.sign_convention_guard as guard

    async def _check(db, project_id, year):  # noqa: ANN001, ARG001
        return _Readiness(ready=False, has_legacy=True, warning="旧约定残留")

    monkeypatch.setattr(guard, "check_sign_convention_readiness", _check)


def _tb(
    project_id: uuid.UUID, code: str, category: str, amount: str, *, company_code: str = "MAIN",
) -> TrialBalance:
    return TrialBalance(
        project_id=project_id, year=YEAR, company_code=company_code, standard_account_code=code, account_name=code,
        account_category=category, audited_amount=Decimal(amount), unadjusted_amount=Decimal(amount),
    )


@asynccontextmanager
async def _world(*rows_for):
    """落库给定试算表行，返回（会话, 本项目 id）。``rows_for`` 收 ``(项目 id, 行)`` 构造函数。"""
    project_id = uuid.uuid4()
    async with make_db(extra_models=[TrialBalance]) as factory:
        async with factory() as db:
            for build in rows_for:
                for item in build(project_id):
                    db.add(item)
            await db.commit()
        async with factory() as db:
            yield db, project_id


@pytest.mark.asyncio
async def test_clean_v2_trial_balance_has_no_warning(no_legacy):
    async with _world(lambda pid: [_tb(pid, "6001", "revenue", "1000.00"),
                                   _tb(pid, "6401", "expense", "600.00")]) as (db, project_id):
        assert await stale_trial_balance_warning(db, project_id, YEAR) is None


@pytest.mark.asyncio
async def test_legacy_sign_convention_rows_trigger_warning(has_legacy):
    async with _world(lambda pid: [_tb(pid, "6001", "revenue", "1000.00")]) as (db, project_id):
        note = await stale_trial_balance_warning(db, project_id, YEAR)
        assert note is not None and STALE_WARNING in note
        assert "旧符号约定" in note


@pytest.mark.asyncio
async def test_negative_credit_pl_account_triggers_warning_and_names_account(no_legacy):
    """真库形态：华氏 6001 审定数为负（design §1 第 9 行）。"""
    async with _world(lambda pid: [_tb(pid, "6001", "revenue", "-20283811823.52"),
                                   _tb(pid, "6051", "revenue", "10.00")]) as (db, project_id):
        assert await negative_credit_pl_accounts(db, project_id, YEAR) == ["6001"]
        note = await stale_trial_balance_warning(db, project_id, YEAR)
        assert note is not None and "6001" in note and "审定数为负" in note


@pytest.mark.asyncio
async def test_misclassified_revenue_still_uses_direction_resolver(no_legacy):
    """历史 6001 被误标 expense（design §1 第 12 行）仍须按编码 / 名称判为贷方并提示。"""
    async with _world(lambda pid: [_tb(pid, "6001", "expense", "-1000.00")]) as (db, project_id):
        assert await negative_credit_pl_accounts(db, project_id, YEAR) == ["6001"]
        note = await stale_trial_balance_warning(db, project_id, YEAR)
        assert note is not None and "6001" in note


@pytest.mark.asyncio
async def test_same_account_in_multiple_companies_is_reported_once(no_legacy):
    async with _world(lambda pid: [
        _tb(pid, "6001", "revenue", "-10.00", company_code="A"),
        _tb(pid, "6001", "revenue", "-20.00", company_code="B"),
    ]) as (db, project_id):
        assert await negative_credit_pl_accounts(db, project_id, YEAR) == ["6001"]


@pytest.mark.asyncio
async def test_negative_expense_account_is_not_flagged(no_legacy):
    """费用类（借方性质）为负不在本判据内 —— 只看贷方性质的损益科目。"""
    async with _world(lambda pid: [_tb(pid, "6401", "expense", "-600.00"),
                                   _tb(pid, "6001", "revenue", "1000.00")]) as (db, project_id):
        assert await negative_credit_pl_accounts(db, project_id, YEAR) == []
        assert await stale_trial_balance_warning(db, project_id, YEAR) is None


@pytest.mark.asyncio
async def test_both_reasons_are_reported_together(has_legacy):
    async with _world(lambda pid: [_tb(pid, "6001", "revenue", "-1.00")]) as (db, project_id):
        note = await stale_trial_balance_warning(db, project_id, YEAR)
        assert note is not None
        assert "旧符号约定" in note and "审定数为负" in note


@pytest.mark.asyncio
async def test_other_project_and_year_rows_do_not_leak(no_legacy):
    """提示按项目 + 年度隔离：别的项目 / 别的年度的坏数据不算在本项目头上。"""
    other = uuid.uuid4()
    async with _world(
        lambda pid: [_tb(pid, "6001", "revenue", "1000.00"), _tb(other, "6001", "revenue", "-999.00")],
    ) as (db, project_id):
        assert await negative_credit_pl_accounts(db, project_id, YEAR) == []
        assert await negative_credit_pl_accounts(db, other, YEAR) == ["6001"]


@pytest.mark.asyncio
async def test_other_year_rows_do_not_leak(no_legacy):
    async with _world(lambda pid: [_tb(pid, "6001", "revenue", "1000.00")]) as (db, project_id):
        assert await negative_credit_pl_accounts(db, project_id, YEAR + 1) == []


@pytest.mark.asyncio
async def test_check_failure_does_not_block_generation(monkeypatch):
    """下一层抛错时只记日志、不抛给报表生成（fail-open，提示性检查）。"""
    import app.services.ledger_import.sign_convention_guard as guard

    async def _boom(db, project_id, year):  # noqa: ANN001, ARG001
        raise RuntimeError("探表失败")

    monkeypatch.setattr(guard, "check_sign_convention_readiness", _boom)
    async with _world(lambda pid: [_tb(pid, "6001", "revenue", "1000.00")]) as (db, project_id):
        assert await stale_trial_balance_warning(db, project_id, YEAR) is None


@pytest.mark.asyncio
async def test_sql_failure_is_rolled_back_to_savepoint(monkeypatch, no_legacy):
    """提示查询 SQL 失败后外层事务仍可用；只 catch 不用保存点时，PG 上下一条查询会报 transaction aborted。"""
    import sqlalchemy as sa
    import app.services.report_tb_staleness as module

    original = module.negative_credit_pl_accounts

    async def _bad_sql(db, project_id, year, *, limit=5):  # noqa: ANN001, ARG001
        await db.execute(sa.text("SELECT * FROM s9_table_that_does_not_exist"))
        return []

    monkeypatch.setattr(module, "negative_credit_pl_accounts", _bad_sql)
    async with _world(lambda pid: [_tb(pid, "6001", "revenue", "1000.00")]) as (db, project_id):
        assert await stale_trial_balance_warning(db, project_id, YEAR) is None
        # 关键断言：提示性检查失败以后，外层会话仍能继续执行 SQL
        assert (await db.execute(sa.select(sa.literal(1)))).scalar_one() == 1
    monkeypatch.setattr(module, "negative_credit_pl_accounts", original)
