"""H 循环 =LEDGER 公式（H1-12 折旧测算表 =LEDGER('1602','credit','X月')）。

formula-fetch-followup-defect-closure 6.5 改写：原文件 import ``_FORMULA_RE`` / ``_FORMULA_RESOLVERS`` /
``_resolve_ledger_formula``（``2638b32fd`` 删除 / 改延迟构建）整文件收集即错；原取数用例全是 mock DB（返回什么断言什么，
测不到 SQL 条件）。现按现行路径：识别 = ``_get_formula_re()``；取数 = ``resolve_extended_formula``（用户公式预览，
内部「预载 → L1」）在真 SQLite 序时账上求值：逐月 / 半年 / 全年 / 借贷方向 / 已删除行 / 其他项目与年度隔离按值断言；
方向或期间写错 ⇒ 取不到（原先方向不认识按贷方取、期间不认识按全年取，给的是错数）。

Validates: Requirements H-F10
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.services.prefill_engine import _get_formula_re, _parse_args, _parse_period_range, resolve_extended_formula

_PID = uuid.UUID("cccc1602-0000-4000-8000-000000000001")
_OTHER_PID = uuid.UUID("cccc1602-0000-4000-8000-000000000002")
_YEAR = 2025


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    """1602 累计折旧逐月贷方 m×1000（6 月另有借方 777）；1601 3 月借方 500000、4 月 1000；
    干扰行：已删除、其他项目、上一年度各一条 6 月 1602 贷方。"""
    from app.models.audit_platform_models import TbLedger

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        def row(pid, year, month, code, debit, credit, no, deleted=False):
            s.add(TbLedger(project_id=pid, year=year, company_code="001", voucher_date=date(year, month, 15),
                           voucher_no=no, account_code=code, account_name="", accounting_period=month,
                           debit_amount=Decimal(debit), credit_amount=Decimal(credit), is_deleted=deleted))

        for m in range(1, 13):
            row(_PID, _YEAR, m, "1602", "0", str(m * 1000), f"记-{m:02d}")
        row(_PID, _YEAR, 6, "1602", "777", "0", "记-06-借")
        row(_PID, _YEAR, 3, "1601", "500000", "0", "记-03-原值")
        row(_PID, _YEAR, 4, "1601", "1000", "0", "记-04-原值")
        row(_PID, _YEAR, 6, "1602", "0", "99999", "记-06-删", deleted=True)
        row(_OTHER_PID, _YEAR, 6, "1602", "0", "55555", "记-06-他项目")
        row(_PID, _YEAR - 1, 6, "1602", "0", "44444", "记-06-上年")
        await s.commit()
        yield s
    await engine.dispose()


async def _ledger(db: AsyncSession, raw_args: str):
    return await resolve_extended_formula(db, _PID, _YEAR, "LEDGER", raw_args)


# ---------------------------------------------------------------------------
# 1. 公式识别与参数解析（解析层）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "formula,expected_args",
    [
        ("=LEDGER('1602','credit','1月')", "'1602','credit','1月'"),
        ("=LEDGER('1602','credit','12月')", "'1602','credit','12月'"),
        ("=LEDGER('1602','credit','全年')", "'1602','credit','全年'"),
        ("=LEDGER('1602','credit','1-6月')", "'1602','credit','1-6月'"),
        ("=LEDGER('1601','debit','3月')", "'1601','debit','3月'"),
    ],
)
def test_formula_re_recognizes_h_cycle_ledger(formula, expected_args):
    m = _get_formula_re().search(formula)
    assert m is not None, f"公式正则未识别 {formula}"
    assert m.group(1).upper() == "LEDGER"
    assert m.group(2).strip() == expected_args


@pytest.mark.parametrize(
    "period,expected",
    [("1月", (1, 1)), ("6月", (6, 6)), ("12月", (12, 12)), ("1-6月", (1, 6)), ("7-12月", (7, 12)), ("全年", (1, 12))],
)
def test_parse_period_range_h_cycle_formats(period, expected):
    assert _parse_period_range(period) == expected


def test_parse_args_h_cycle_ledger():
    assert _parse_args("'1602','credit','1-6月'") == ["1602", "credit", "1-6月"]


# ---------------------------------------------------------------------------
# 2. 真库取数：期间 / 方向 / 隔离
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_args,expected",
    [
        ("'1602','credit','6月'", Decimal("6000")),       # 单月；已删除 / 他项目 / 上年的 6 月行不计入
        ("'1602','credit','1-6月'", Decimal("21000")),    # 半年
        ("'1602','credit','7-12月'", Decimal("57000")),
        ("'1602','credit','全年'", Decimal("78000")),     # 全年不加期间条件
        ("'1602','credit'", Decimal("78000")),             # 两参：期间缺省全年
        ("'1602','debit','6月'", Decimal("777")),         # 方向：同月借方另算
        ("'1601','debit','3月'", Decimal("500000")),
        ("'1601','借','3-4月'", Decimal("501000")),       # 中文方向
        ("'1602','贷','12月'", Decimal("12000")),
        ("'9999','credit','全年'", Decimal("0")),         # 科目没有发生额：合法的 0
    ],
)
async def test_ledger_values_on_real_rows(db, raw_args, expected):
    assert await _ledger(db, raw_args) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_args",
    [
        "'1602','期末数量','全年'",   # 方向不认识：原先按贷方取（得 78000），映射表 F2 盘点表有 9 格这样写
        "'1602','credit','13月'",     # 月份越界：原先按 13 月查（得 0）
        "'1602','credit','上半年'",   # 期间不认识：原先不加条件按全年取（得 78000）
        "'1602'",                     # 少参：L1 默认借方全年，预载层不扫一参写法
    ],
)
async def test_unrecognized_direction_or_period_is_not_a_number(db, raw_args):
    """方向 / 期间写错 ⇒ 取不到（None），不给按贷方 / 全年 / 0 凑出来的数。"""
    assert await _ledger(db, raw_args) is None
