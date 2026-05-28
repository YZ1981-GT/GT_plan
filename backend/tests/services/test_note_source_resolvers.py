"""单测 — 7 种 source 数据源解析器（Sprint 1 Task 1.4）.

Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 1 Task 1.4
Reqs:   R1.2 七种数据源支持

每种 source 至少 3 用例 + 完整性 + dispatch。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.note_source_resolvers import (
    SOURCE_RESOLVERS,
    VALID_SOURCES,
    dispatch_resolver,
    resolve_aux_balance,
    resolve_aux_ledger_aging,
    resolve_formula,
    resolve_ledger_sum,
    resolve_manual,
    resolve_prior_year_note,
    resolve_trial_balance,
)

# ---------------------------------------------------------------------------
# 通用 helper：mock db.execute → result.scalar() / result.all()
# ---------------------------------------------------------------------------


def _make_db_with_scalar(value: Any) -> MagicMock:
    """模拟 db.execute() → result.scalar() = value."""
    db = MagicMock()
    result = MagicMock()
    result.scalar = MagicMock(return_value=value)
    db.execute = AsyncMock(return_value=result)
    return db


def _make_db_with_all(rows: list[Any]) -> MagicMock:
    """模拟 db.execute() → result.all() = rows."""
    db = MagicMock()
    result = MagicMock()
    result.all = MagicMock(return_value=rows)
    db.execute = AsyncMock(return_value=result)
    return db


def _ctx(project_id=None, year=2025, db=None, **overrides) -> dict:
    base: dict = {
        "project_id": project_id or uuid4(),
        "year": year,
        "db": db,
        "_tb_cache": {},
        "_wp_cache": {},
        "_prior_notes_cache": {},
    }
    base.update(overrides)
    return base


# ===========================================================================
# 1) trial_balance
# ===========================================================================


@pytest.mark.asyncio
async def test_trial_balance_single_account_hit():
    """单 account 命中并返回 audited_amount."""
    ctx = _ctx()
    ctx["_tb_cache"]["1001"] = {"audited": 1234.5, "opening": 100.0, "unadjusted": 1234.5}
    binding = {
        "source": "trial_balance",
        "field": "audited_amount",
        "account_codes": ["1001"],
        "agg": "sum",
    }
    val = await resolve_trial_balance(binding, ctx)
    assert val == 1234.5


@pytest.mark.asyncio
async def test_trial_balance_multi_account_sum():
    """多 account 求和."""
    ctx = _ctx()
    ctx["_tb_cache"]["1001"] = {"audited": 1000.0, "opening": 0, "unadjusted": 0}
    ctx["_tb_cache"]["1002"] = {"audited": 500.0, "opening": 0, "unadjusted": 0}
    binding = {
        "source": "trial_balance",
        "field": "audited_amount",
        "account_codes": ["1001", "1002"],
        "agg": "sum",
    }
    val = await resolve_trial_balance(binding, ctx)
    assert val == 1500.0


@pytest.mark.asyncio
async def test_trial_balance_missing_data_returns_none():
    """缓存未命中（缺 account / 空缓存）返回 None."""
    ctx = _ctx()
    binding = {
        "source": "trial_balance",
        "field": "audited_amount",
        "account_codes": ["9999"],
    }
    val = await resolve_trial_balance(binding, ctx)
    assert val is None


@pytest.mark.asyncio
async def test_trial_balance_opening_balance_field():
    """field=opening_balance 走 cache.opening 通道."""
    ctx = _ctx()
    ctx["_tb_cache"]["2001"] = {"audited": 0, "opening": 222.0, "unadjusted": 0}
    binding = {
        "source": "trial_balance",
        "field": "opening_balance",
        "account_codes": ["2001"],
    }
    val = await resolve_trial_balance(binding, ctx)
    assert val == 222.0


@pytest.mark.asyncio
async def test_trial_balance_sum_minus_negates():
    """agg=sum_minus 取相反数（用于负债类）."""
    ctx = _ctx()
    ctx["_tb_cache"]["2201"] = {"audited": 100.0, "opening": 0, "unadjusted": 0}
    binding = {
        "source": "trial_balance",
        "field": "audited_amount",
        "account_codes": ["2201"],
        "agg": "sum_minus",
    }
    val = await resolve_trial_balance(binding, ctx)
    assert val == -100.0


# ===========================================================================
# 2) ledger_sum (period_filter 三模式)
# ===========================================================================


@pytest.mark.asyncio
async def test_ledger_sum_year_range():
    """period_filter.mode=year_range 求和."""
    db = _make_db_with_scalar(Decimal("8888.88"))
    ctx = _ctx(db=db)
    binding = {
        "source": "ledger_sum",
        "field": "debit_amount",
        "account_codes": ["6001"],
        "period_filter": {
            "mode": "year_range",
            "start": "2025-01-01",
            "end": "2025-12-31",
        },
    }
    val = await resolve_ledger_sum(binding, ctx)
    assert val == 8888.88
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_ledger_sum_month_range():
    """period_filter.mode=month_range 用 accounting_period.between."""
    db = _make_db_with_scalar(100.0)
    ctx = _ctx(db=db)
    binding = {
        "source": "ledger_sum",
        "field": "credit_amount",
        "account_codes": ["6001"],
        "period_filter": {"mode": "month_range", "start": 1, "end": 6},
    }
    val = await resolve_ledger_sum(binding, ctx)
    assert val == 100.0


@pytest.mark.asyncio
async def test_ledger_sum_missing_data_returns_zero_or_none():
    """db.scalar 返 0 → 0.0；缺 db / 缺 codes → None."""
    # db 缺
    val = await resolve_ledger_sum(
        {"source": "ledger_sum", "field": "debit_amount", "account_codes": ["X"]},
        _ctx(db=None),
    )
    assert val is None
    # account_codes 缺
    val = await resolve_ledger_sum(
        {"source": "ledger_sum", "field": "debit_amount", "account_codes": []},
        _ctx(db=_make_db_with_scalar(0)),
    )
    assert val is None


@pytest.mark.asyncio
async def test_ledger_sum_var_substitution_current_year():
    """${current_year} 变量插值生效."""
    db = _make_db_with_scalar(Decimal("123"))
    ctx = _ctx(db=db, year=2025)
    binding = {
        "source": "ledger_sum",
        "field": "debit_amount",
        "account_codes": ["6001"],
        "period_filter": {
            "mode": "date_range",
            "start": "${current_year}-01-01",
            "end": "${current_year}-12-31",
        },
    }
    val = await resolve_ledger_sum(binding, ctx)
    assert val == 123.0


# ===========================================================================
# 3) aux_balance
# ===========================================================================


@pytest.mark.asyncio
async def test_aux_balance_with_aux_type_filter():
    """aux_type 过滤生效（仅 SQL 验证不报错 + 返回值）."""
    db = _make_db_with_scalar(Decimal("777"))
    ctx = _ctx(db=db)
    binding = {
        "source": "aux_balance",
        "field": "closing_balance",
        "account_codes": ["1122"],
        "aux_type": "customer",
    }
    val = await resolve_aux_balance(binding, ctx)
    assert val == 777.0


@pytest.mark.asyncio
async def test_aux_balance_sum_no_aux_type():
    """无 aux_type 走纯 account_codes 求和."""
    db = _make_db_with_scalar(Decimal("500"))
    ctx = _ctx(db=db)
    binding = {
        "source": "aux_balance",
        "field": "opening_balance",
        "account_codes": ["1122"],
    }
    val = await resolve_aux_balance(binding, ctx)
    assert val == 500.0


@pytest.mark.asyncio
async def test_aux_balance_missing_data_returns_none():
    """缺 db / 缺 codes / db.scalar=None 走 None / 0 分支."""
    val = await resolve_aux_balance(
        {"source": "aux_balance", "field": "closing_balance", "account_codes": []},
        _ctx(db=_make_db_with_scalar(0)),
    )
    assert val is None
    val = await resolve_aux_balance(
        {"source": "aux_balance", "field": "closing_balance", "account_codes": ["X"]},
        _ctx(db=None),
    )
    assert val is None


# ===========================================================================
# 4) aux_ledger_aging
# ===========================================================================


@pytest.mark.asyncio
async def test_aux_ledger_aging_single_bucket_within_1y():
    """单桶：1年以内，年末 2025-12-31 - 凭证 2025-06-01 = 213 天 → 1年以内."""
    rows = [
        (date(2025, 6, 1), Decimal("1000"), Decimal("0")),
    ]
    db = _make_db_with_all(rows)
    ctx = _ctx(db=db, year=2025)
    binding = {
        "source": "aux_ledger_aging",
        "field": "bucket_amount",
        "account_codes": ["1122"],
        "bucket": "1年以内",
    }
    val = await resolve_aux_ledger_aging(binding, ctx)
    assert val == 1000.0


@pytest.mark.asyncio
async def test_aux_ledger_aging_multi_bucket():
    """多桶：3 行分别落 1年内 / 1-2年 / 5年以上 — 取 1-2年 桶."""
    rows = [
        (date(2025, 6, 1), Decimal("100"), Decimal("0")),  # 213 天 → 1年以内
        (date(2024, 6, 1), Decimal("200"), Decimal("0")),  # 578 天 → 1-2年
        (date(2018, 1, 1), Decimal("300"), Decimal("0")),  # 5年以上
    ]
    db = _make_db_with_all(rows)
    ctx = _ctx(db=db, year=2025)
    binding = {
        "source": "aux_ledger_aging",
        "field": "bucket_amount",
        "account_codes": ["1122"],
        "bucket": "1-2年",
    }
    val = await resolve_aux_ledger_aging(binding, ctx)
    assert val == 200.0


@pytest.mark.asyncio
async def test_aux_ledger_aging_no_aux_data_returns_none():
    """客户未提供辅助序时账（rows=[]）返回 None — caller 据此判定 not_applicable.

    Validates: Requirements 7
    """
    db = _make_db_with_all([])
    ctx = _ctx(db=db, year=2025)
    binding = {
        "source": "aux_ledger_aging",
        "field": "bucket_amount",
        "account_codes": ["1122"],
        "bucket": "1年以内",
    }
    val = await resolve_aux_ledger_aging(binding, ctx)
    assert val is None


@pytest.mark.asyncio
async def test_aux_ledger_aging_unknown_bucket_returns_none():
    """未识别桶名返回 None（不抛错）."""
    db = _make_db_with_all([(date(2025, 6, 1), Decimal("1"), Decimal("0"))])
    ctx = _ctx(db=db, year=2025)
    binding = {
        "source": "aux_ledger_aging",
        "field": "bucket_amount",
        "account_codes": ["1122"],
        "bucket": "10年以上",  # 不在 _AGING_BUCKETS
    }
    val = await resolve_aux_ledger_aging(binding, ctx)
    assert val is None


# ===========================================================================
# 5) formula (stub — Sprint 1.5 实装)
# ===========================================================================


@pytest.mark.asyncio
async def test_formula_stub_returns_none():
    """1.4 stub：永远 None.."""
    val = await resolve_formula({"source": "formula", "expr": "TB('a','期末')"}, _ctx())
    assert val is None


@pytest.mark.asyncio
async def test_formula_does_not_raise():
    """空 binding / 缺 expr 不抛错."""
    val = await resolve_formula({}, _ctx())
    assert val is None


@pytest.mark.asyncio
async def test_formula_signature_async():
    """接口签名校验：async + 接受 (binding, ctx)."""
    import inspect
    assert inspect.iscoroutinefunction(resolve_formula)
    sig = inspect.signature(resolve_formula)
    assert list(sig.parameters.keys()) == ["binding", "ctx"]


# ===========================================================================
# 6) prior_year_note
# ===========================================================================


@pytest.mark.asyncio
async def test_prior_year_note_text_from_cache():
    """field=text → cache 命中返回字符串."""
    ctx = _ctx()
    ctx["_prior_notes_cache"]["五、1 货币资金"] = "本期货币资金主要为银行存款……"
    binding = {
        "source": "prior_year_note",
        "field": "text",
        "section": "五、1 货币资金",
    }
    val = await resolve_prior_year_note(binding, ctx)
    assert "货币资金" in val


@pytest.mark.asyncio
async def test_prior_year_note_missing_returns_none():
    """缺 cache / 缺 section → None（不抛错）.

    Validates: Requirements 9
    """
    ctx = _ctx()
    val = await resolve_prior_year_note({"source": "prior_year_note", "field": "text"}, ctx)
    assert val is None


@pytest.mark.asyncio
async def test_prior_year_note_unicode_section_via_ctx():
    """中文 section_number 通过 ctx['section_number'] 兜底."""
    ctx = _ctx()
    ctx["_prior_notes_cache"]["十、1 长期股权投资"] = "上年附注正文"
    ctx["section_number"] = "十、1 长期股权投资"
    binding = {"source": "prior_year_note", "field": "text"}
    val = await resolve_prior_year_note(binding, ctx)
    assert val == "上年附注正文"


# ===========================================================================
# 7) manual
# ===========================================================================


@pytest.mark.asyncio
async def test_manual_returns_binding_value():
    """直接读 binding.manual_value."""
    val = await resolve_manual({"source": "manual", "manual_value": 42.0}, _ctx())
    assert val == 42.0


@pytest.mark.asyncio
async def test_manual_missing_returns_none():
    """缺 manual_value → None."""
    val = await resolve_manual({"source": "manual"}, _ctx())
    assert val is None


@pytest.mark.asyncio
async def test_manual_type_safe():
    """非 dict 输入不抛错（防御）."""
    val = await resolve_manual(None, _ctx())  # type: ignore[arg-type]
    assert val is None
    val = await resolve_manual({"source": "manual", "manual_value": "hand"}, _ctx())
    assert val == "hand"


# ===========================================================================
# 完整性 + dispatcher
# ===========================================================================


def test_source_resolvers_keys_match_valid_sources():
    """SOURCE_RESOLVERS 与 VALID_SOURCES 对齐 — CI 卡点."""
    assert set(SOURCE_RESOLVERS.keys()) == set(VALID_SOURCES)
    assert len(VALID_SOURCES) == 9


def test_all_resolvers_callable():
    """每个 resolver 都是 async callable."""
    import inspect
    for src, fn in SOURCE_RESOLVERS.items():
        assert inspect.iscoroutinefunction(fn), f"{src} resolver not async"


@pytest.mark.asyncio
async def test_dispatch_resolver_routes_correctly():
    """dispatch_resolver 按 source 路由到对应函数."""
    ctx = _ctx()
    ctx["_tb_cache"]["1001"] = {"audited": 99.0, "opening": 0, "unadjusted": 0}
    val = await dispatch_resolver(
        {"source": "trial_balance", "field": "audited_amount", "account_codes": ["1001"]},
        ctx,
    )
    assert val == 99.0


@pytest.mark.asyncio
async def test_dispatch_resolver_unknown_source_returns_none():
    """未识别 source / 缺 source → None."""
    val = await dispatch_resolver({"source": "unknown_xxx"}, _ctx())
    assert val is None
    val = await dispatch_resolver({}, _ctx())
    assert val is None
    val = await dispatch_resolver(None, _ctx())  # type: ignore[arg-type]
    assert val is None


@pytest.mark.asyncio
async def test_dispatch_resolver_swallows_exceptions():
    """resolver 抛错 → dispatcher 兜底返 None（不传染上层）."""
    db = MagicMock()
    db.execute = AsyncMock(side_effect=RuntimeError("boom"))
    ctx = _ctx(db=db)
    val = await dispatch_resolver(
        {"source": "ledger_sum", "field": "debit_amount", "account_codes": ["X"]},
        ctx,
    )
    assert val is None
