"""K 管理循环 —— ``=LEDGER_DETAIL('科目','期间','金额条件')`` 真库取数。

Spec: .kiro/specs/k-admin-cycle-post-review-fix/ Sprint 1 Task 3.4（K8-2 / K9-2 销售 / 管理费用月度明细）。

formula-fetch-followup-defect-closure 6.5 改写：原文件测 ``prefill_engine._resolve_ledger_detail_formula``，该函数自
formula-execution-path-convergence 起已无调用方、``2638b32fd`` 删除，整文件收集即错。收敛后的路径里预载层从不取明细
（``preload`` 写死 ``ledger_detail_data={}``）⇒ L1 ``LEDGER_DETAIL`` 恒为 0 笔 —— 映射表 56 格预设全部取不到。
现在预载层 ``_load_ledger_detail`` 取明细（与原实现同口径：科目精确 / 含 ``%`` 按 LIKE，金额条件对借方或贷方任一侧
成立即命中，按凭证日期 / 凭证号排序），L1 按笔数给值；期间 / 金额条件不认识、超过行数上限 ⇒ 取不到（不给错数）。
原 5 例的数据与命中断言原样保留，改为对预载层明细行断言，并补 L1 端到端笔数。
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.services import formula_preloader
from app.services.prefill_engine import resolve_extended_formula

FAKE_PROJECT_ID = uuid.uuid4()
YEAR = 2025
REQUIRED_ROW_KEYS = {"voucher_date", "voucher_no", "summary", "debit_amount", "credit_amount", "counterpart_account"}


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """K8 销售费用 6601：1 月借 500 / 贷 200 / 借 -100（红字）、2 月借 800；K9 管理费用 6602：1 月借 1000。"""
    from app.models.audit_platform_models import TbLedger

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        for vno, code, name, d, period, debit, credit, cp, summary in (
            ("记-K8-001", "6601", "销售费用", date(2025, 1, 5), 1, "500.00", "0", "1001", "销售人员差旅费"),
            ("记-K8-002", "6601", "销售费用", date(2025, 1, 12), 1, "0", "200.00", "1002", "销售费用冲回"),
            ("记-K8-003", "6601", "销售费用", date(2025, 1, 20), 1, "-100.00", "0", "1003", "销售费用红字调整"),
            ("记-K8-004", "6601", "销售费用", date(2025, 2, 3), 2, "800.00", "0", "1001", "销售人员差旅费"),
            ("记-K9-001", "6602", "管理费用", date(2025, 1, 8), 1, "1000.00", "0", "1002", "办公用品采购"),
        ):
            s.add(TbLedger(project_id=FAKE_PROJECT_ID, year=YEAR, company_code="001", voucher_date=d, voucher_no=vno,
                           account_code=code, account_name=name, accounting_period=period,
                           debit_amount=Decimal(debit), credit_amount=Decimal(credit), counterpart_account=cp,
                           summary=summary))
        await s.commit()
        yield s
    await engine.dispose()


async def _rows(db: AsyncSession, code: str, period: str, amount_filter: str):
    """预载层明细行；没取（条件不认识 / 超上限）返回 None。"""
    loaded = await formula_preloader._load_ledger_detail(db, FAKE_PROJECT_ID, YEAR, {(code, period, amount_filter)})
    return loaded.get(f"{code}:{period}:{amount_filter}")


async def _count(db: AsyncSession, raw_args: str):
    return await resolve_extended_formula(db, FAKE_PROJECT_ID, YEAR, "LEDGER_DETAIL", raw_args)


def _assert_row_shape(row: dict) -> None:
    missing = REQUIRED_ROW_KEYS - row.keys()
    assert not missing, f"明细行缺少字段 {missing}：{row!r}"


@pytest.mark.asyncio
async def test_direction_geq_zero_hits_all_three_january_rows(db_session):
    """'>=0'：借方或贷方任一侧 >= 0 即命中 ⇒ 6601 / 1 月三条全中（红字那条贷方为 0 也满足）；6602 不混入。"""
    rows = await _rows(db_session, "6601", "1月", ">=0")
    assert [r["voucher_no"] for r in rows] == ["记-K8-001", "记-K8-002", "记-K8-003"]  # 按凭证日期排序
    for row in rows:
        _assert_row_shape(row)
    assert await _count(db_session, "'6601','1月','>=0'") == Decimal("3")


@pytest.mark.asyncio
async def test_direction_lt_zero_hits_only_red_entry(db_session):
    rows = await _rows(db_session, "6601", "1月", "<0")
    assert [r["voucher_no"] for r in rows] == ["记-K8-003"]
    assert rows[0]["debit_amount"] == "-100.00" and rows[0]["summary"] == "销售费用红字调整"
    assert await _count(db_session, "'6601','1月','<0'") == Decimal("1")


@pytest.mark.asyncio
async def test_wildcard_keeps_period_filter(db_session):
    """'*' 不过滤金额，但期间照样过滤：2 月那条（记-K8-004）不在 1 月结果里。"""
    rows = await _rows(db_session, "6601", "1月", "*")
    assert {r["voucher_no"] for r in rows} == {"记-K8-001", "记-K8-002", "记-K8-003"}
    assert await _count(db_session, "'6601','1月','*'") == Decimal("3")
    assert await _count(db_session, "'6601','全年','*'") == Decimal("4")
    assert await _count(db_session, "'6601'") == Decimal("4")  # 一参：期间全年、金额不过滤


@pytest.mark.asyncio
async def test_no_rows_is_a_legit_zero(db_session):
    """科目当年没有流水（6603 财务费用）⇒ 0 笔，是合法的 0（取到了、没有命中）。"""
    assert await _rows(db_session, "6603", "全年", "*") == []
    assert await _count(db_session, "'6603','全年','*'") == Decimal("0")


@pytest.mark.asyncio
async def test_account_filter_isolation_and_like(db_session):
    rows = await _rows(db_session, "6602", "1月", ">=0")
    assert [r["voucher_no"] for r in rows] == ["记-K9-001"]
    assert await _count(db_session, "'66%','1月','>=0'") == Decimal("4")  # 含 % 按 LIKE：6601 三条 + 6602 一条


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_args",
    [
        "'6601','1月','大于100'",                           # 金额条件不认识：原实现静默不过滤（按全部行计）
        "'6601','上半年','*'",                              # 期间不认识：原实现不加期间条件（按全年计）
        "'2211','月度分析表J1-4','1月','期末余额'",         # J1 四参写法（映射表 21 格）：不是明细筛选
    ],
)
async def test_unrecognized_condition_is_not_a_number(db_session, raw_args):
    assert await _count(db_session, raw_args) is None


@pytest.mark.asyncio
async def test_over_limit_is_not_truncated_count(db_session, monkeypatch):
    """符合条件超过行数上限 ⇒ 不取（L1 按行数给值，截断后的行数是错数）；上限以内照常。"""
    monkeypatch.setattr(formula_preloader, "LEDGER_DETAIL_LIMIT", 2)
    assert await _rows(db_session, "6601", "1月", "*") is None
    assert await _count(db_session, "'6601','1月','*'") is None
    assert await _count(db_session, "'6601','1月','<0'") == Decimal("1")
