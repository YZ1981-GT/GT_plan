# Feature: formula-management-library, Property 2: 前置校验阻断残缺数据
"""属性测试 P2：四表库前置校验阻断残缺数据（Task 5.7）。

**Property 2: 前置校验阻断残缺数据**

*对任意*四表库完整度状态（tb_balance / trial_balance 有无、tb_ledger / tb_aux_balance
有无、试算表未审数是否全 0），``DraftRefreshService.precheck`` 满足：

- **核心表缺失**（tb_balance 或 trial_balance 任一无该项目/年度数据）→ ``blocking``
  非空、``can_refresh=False``，且每条阻断项都含表名（table/label）与说明（message）。
  阻断项恰好覆盖缺失的核心表集合。
- **核心表齐全** → ``can_refresh=True``、``blocking`` 为空；次级来源缺失
  （tb_ledger / tb_aux_balance）或未审数全 0 只进 ``warnings``（非阻断）。

**Validates: Requirements 2.1, 2.2**

被测：``app.services.draft_refresh_service.DraftRefreshService.precheck``。
用内存 sqlite（参考 tests/test_draft_refresh_precheck.py 的 fixture/种子）。

Framework: hypothesis（遵循 conftest fast profile，max_examples 可经
HYPOTHESIS_MAX_EXAMPLES 覆盖）。
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st
from sqlalchemy import MetaData
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

# sqlite 无原生 JSONB / ARRAY：映射到 JSON / TEXT（与 test_draft_refresh_precheck.py 一致）。
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.audit_platform_models import (  # noqa: E402
    AccountCategory,
    TbAuxBalance,
    TbBalance,
    TbLedger,
    TrialBalance,
)
from app.models.dataset_models import LedgerDataset  # noqa: E402
from app.services.draft_refresh_service import DraftRefreshService  # noqa: E402

PROJECT_ID = uuid.uuid4()
YEAR = 2025

_TEST_TABLES = [
    TbBalance.__table__,
    TbLedger.__table__,
    TbAuxBalance.__table__,
    TrialBalance.__table__,
    LedgerDataset.__table__,
]


# ─────────────────────────────────────────────────────────────────────────────
# 事件循环辅助 + 独立内存 sqlite（每个 example 全新库，隔离种子副作用）。
# hypothesis 与 function-scoped async fixture 不兼容，改用同步 _run 包装。
# ─────────────────────────────────────────────────────────────────────────────
def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _make_session() -> tuple[async_sessionmaker, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sc: MetaData().create_all(sc, tables=_TEST_TABLES)
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return factory, engine


# ── 种子行构造（参考 test_draft_refresh_precheck.py）──────────────────────────
def _tb_balance() -> TbBalance:
    return TbBalance(
        project_id=PROJECT_ID, year=YEAR, company_code="C1",
        account_code="1001", account_name="库存现金",
        closing_balance=Decimal("100"),
    )


def _trial_balance(unadjusted: Decimal) -> TrialBalance:
    return TrialBalance(
        project_id=PROJECT_ID, year=YEAR, company_code="C1",
        standard_account_code="1001", account_name="库存现金",
        account_category=AccountCategory.asset, unadjusted_amount=unadjusted,
    )


def _tb_ledger() -> TbLedger:
    return TbLedger(
        project_id=PROJECT_ID, year=YEAR, company_code="C1",
        voucher_date=date(YEAR, 1, 1), voucher_no="V1",
        account_code="6001", account_name="主营业务收入",
        credit_amount=Decimal("500"),
    )


def _tb_aux() -> TbAuxBalance:
    return TbAuxBalance(
        project_id=PROJECT_ID, year=YEAR, company_code="C1",
        account_code="1122", account_name="应收账款",
        aux_type="customer", aux_code="K01", aux_name="客户甲",
        closing_balance=Decimal("300"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 智能生成器：随机四表库完整度状态。
# ─────────────────────────────────────────────────────────────────────────────
@given(
    has_tb_balance=st.booleans(),
    has_trial_balance=st.booleans(),
    has_tb_ledger=st.booleans(),
    has_tb_aux=st.booleans(),
    unadjusted_all_zero=st.booleans(),
)
def test_p2_precheck_blocks_on_missing_core_tables(
    has_tb_balance: bool,
    has_trial_balance: bool,
    has_tb_ledger: bool,
    has_tb_aux: bool,
    unadjusted_all_zero: bool,
):
    """P2：核心表缺失→阻断且 can_refresh=False；核心表齐全→次级缺失仅 warnings。

    **Validates: Requirements 2.1, 2.2**
    """

    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                seeds = []
                if has_tb_balance:
                    seeds.append(_tb_balance())
                if has_trial_balance:
                    seeds.append(
                        _trial_balance(
                            Decimal("0") if unadjusted_all_zero else Decimal("100")
                        )
                    )
                if has_tb_ledger:
                    seeds.append(_tb_ledger())
                if has_tb_aux:
                    seeds.append(_tb_aux())
                if seeds:
                    db.add_all(seeds)
                    await db.commit()

                result = await DraftRefreshService().precheck(
                    db, project_id=PROJECT_ID, year=YEAR
                )

                expected_missing_core: set[str] = set()
                if not has_tb_balance:
                    expected_missing_core.add("tb_balance")
                if not has_trial_balance:
                    expected_missing_core.add("trial_balance")

                blocking_tables = {i.table for i in result.blocking}
                warning_tables = {i.table for i in result.warnings}

                # can_refresh 恒等于 blocking 为空（Req 2.2 语义）。
                assert result.can_refresh is (len(result.blocking) == 0)

                if expected_missing_core:
                    # 核心表缺失 → 阻断非空、不可刷新（Req 2.2）。
                    assert result.can_refresh is False, (
                        "核心表缺失时必须阻断刷新"
                    )
                    assert result.blocking, "核心表缺失时 blocking 必须非空"
                    # 阻断项恰好覆盖缺失的核心表集合。
                    assert blocking_tables == expected_missing_core, (
                        f"阻断项 {blocking_tables} 应等于缺失核心表 "
                        f"{expected_missing_core}"
                    )
                    # 每条阻断项含表名 + 中文标签 + 说明（Req 2.1）。
                    for item in result.blocking:
                        assert item.table, "阻断项必须含表名"
                        assert item.label, "阻断项必须含中文标签"
                        assert item.message, "阻断项必须含说明"
                else:
                    # 核心表齐全 → 可刷新、无阻断（Req 2.1）。
                    assert result.can_refresh is True, (
                        "核心表齐全时应可刷新"
                    )
                    assert result.blocking == [], "核心表齐全时不应有阻断项"
                    # 次级来源缺失只进 warnings（非阻断）。
                    if not has_tb_ledger:
                        assert "tb_ledger" in warning_tables, (
                            "缺序时账应产生非阻断告警"
                        )
                    if not has_tb_aux:
                        assert "tb_aux_balance" in warning_tables, (
                            "缺辅助余额表应产生非阻断告警"
                        )
                    # 未审数全 0 → trial_balance 非阻断告警。
                    if unadjusted_all_zero:
                        assert any(
                            i.table == "trial_balance" and "未审数" in i.message
                            for i in result.warnings
                        ), "未审数全 0 应产生初稿可能为空的告警"
                    # 每条告警项同样含表名 + 说明。
                    for item in result.warnings:
                        assert item.table
                        assert item.label
                        assert item.message
        finally:
            await engine.dispose()

    _run(_scenario())
