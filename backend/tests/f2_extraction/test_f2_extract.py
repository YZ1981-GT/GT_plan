"""F2-1 审定表四表库取数核心 — 单元测试.

使用 SQLite 内存 + monkeypatch get_active_filter → sa.literal(True)
12 个用例覆盖 Property 1/2/3/5/8/12:
- parse_tb_formula (valid + invalid)
- _is_leaf
- extract (single/multi-level/impairment-abs/zero/empty/formula-driven/idempotent)
- build_default_bindings (count + impairment abs)
"""
from __future__ import annotations

import types
from collections import namedtuple
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import sqlalchemy as sa

from app.services.f2_extraction.extract import (
    F2_COLUMN_MAP,
    F2_ROW_KEY_ACCOUNT,
    _is_leaf,
    build_default_bindings,
    extract_f2_category_values,
    parse_tb_formula,
)


# ---------------------------------------------------------------------------
# test_parse_tb_formula_valid（4 子用例）
# ---------------------------------------------------------------------------


class TestParseTbFormulaValid:
    """Property 8: 公式驱动取值."""

    def test_basic_tb(self):
        result = parse_tb_formula("TB('1401','期初余额')")
        assert result == ("1401", "期初余额", False)

    def test_abs_tb(self):
        result = parse_tb_formula("ABS(TB('1471','期初余额'))")
        assert result == ("1471", "期初余额", True)

    def test_leading_equals(self):
        result = parse_tb_formula("=TB('1402','借方发生额')")
        assert result == ("1402", "借方发生额", False)

    def test_double_quotes(self):
        result = parse_tb_formula('TB("1406","贷方发生额")')
        assert result == ("1406", "贷方发生额", False)


# ---------------------------------------------------------------------------
# test_parse_tb_formula_invalid（3 子用例）
# ---------------------------------------------------------------------------


class TestParseTbFormulaInvalid:
    """非法/不支持的公式返回 None."""

    def test_unknown_column(self):
        """列名不在 F2_COLUMN_MAP → None."""
        assert parse_tb_formula("TB('1401','未知列')") is None

    def test_empty_expression(self):
        assert parse_tb_formula("") is None
        assert parse_tb_formula("   ") is None

    def test_malformed(self):
        assert parse_tb_formula("SUM(A1:B2)") is None
        assert parse_tb_formula("PREV('1401','期末余额')") is None


# ---------------------------------------------------------------------------
# test_is_leaf（4 子用例）
# ---------------------------------------------------------------------------


class TestIsLeaf:
    """Property 1: 只汇总叶子防双算."""

    def test_leaf_no_children(self):
        assert _is_leaf("1401", ["1401", "1402", "1403"]) is True

    def test_non_leaf_has_children(self):
        assert _is_leaf("1401", ["1401", "1401.01", "1401.02"]) is False

    def test_empty_code(self):
        assert _is_leaf("", ["1401", "1402"]) is True

    def test_single_code(self):
        assert _is_leaf("1401", ["1401"]) is True


# ---------------------------------------------------------------------------
# 辅助: 构造 mock ctx / 模拟 tb_balance 行
# ---------------------------------------------------------------------------

TbRow = namedtuple("TbRow", ["account_code", "opening_balance", "closing_balance",
                              "debit_amount", "credit_amount"])


def _make_ctx(rows_by_prefix: dict[str, list[TbRow]], year: int = 2025):
    """构造 mock ctx (db/project_id/year).

    rows_by_prefix: {account_prefix: [TbRow, ...]}
    """
    import uuid

    pid = uuid.uuid4()

    class FakeResult:
        def __init__(self, rows):
            self._rows = rows

        def fetchall(self):
            return self._rows

    async def fake_execute(stmt):
        # 从 stmt 的 WHERE 中提取 account prefix（简化：返回 all rows matched）
        # 这是简化的 mock，测试通过 rows_by_prefix 控制返回
        # 我们用 _pending_rows 机制
        return FakeResult(fake_execute._pending_rows)

    class FakeDb:
        async def execute(self, stmt):
            # 从 rows_by_prefix 匹配：提取 stmt 中 account 的匹配
            # 简化：用外部设置
            return FakeResult(self._current_rows)

    db = FakeDb()
    db._current_rows = []

    ctx = types.SimpleNamespace(db=db, project_id=pid, year=year)
    return ctx, db


def _patch_active_filter():
    """Monkeypatch get_active_filter → sa.literal(True)."""
    async def _mock_get_active_filter(db, table, project_id, year, **kwargs):
        return sa.literal(True)
    return patch(
        "app.services.f2_extraction.extract.get_active_filter",
        side_effect=_mock_get_active_filter,
    )


# ---------------------------------------------------------------------------
# 更精确的 mock: 替换整个 extract_f2_category_values 内部 DB 调用
# ---------------------------------------------------------------------------


async def _run_extract(rows_by_account: dict[str, list[TbRow]], bindings: list[dict]):
    """辅助：构造 ctx，patch DB 查询，运行 extract."""
    import uuid

    pid = uuid.uuid4()

    class FakeResult:
        def __init__(self, rows):
            self._rows = rows

        def fetchall(self):
            return self._rows

    class FakeDb:
        def __init__(self):
            self._call_log = []

        async def execute(self, stmt):
            # 从 bindings 反推 account prefix
            # 简化：按调用顺序匹配 rows_by_account
            # 真实做法：解析 stmt 的 WHERE account 条件
            # 这里用一个 queue
            if self._call_log:
                account = self._call_log.pop(0)
            else:
                account = None
            rows = rows_by_account.get(account, [])
            return FakeResult(rows)

    db = FakeDb()
    ctx = types.SimpleNamespace(db=db, project_id=pid, year=2025)

    # 按解析出的 account 预填 call_log
    from app.services.f2_extraction.extract import parse_tb_formula
    from collections import OrderedDict
    seen_accounts = OrderedDict()
    for b in bindings:
        r = parse_tb_formula(b.get("expression", ""))
        if r:
            seen_accounts[r[0]] = True
    db._call_log = list(seen_accounts.keys())

    with _patch_active_filter():
        result = await extract_f2_category_values(ctx, bindings)
    return result


# ---------------------------------------------------------------------------
# test_extract_single_level (Property 2: 原值直取+正确 column)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_single_level():
    """原值科目直取 + 正确取 opening_balance column."""
    bindings = [
        {"anchor": "F2-1-gross-raw-materials-opening", "expression": "TB('1401','期初余额')"},
    ]
    rows = {
        "1401": [TbRow("1401", Decimal("100000"), Decimal("120000"),
                       Decimal("30000"), Decimal("10000"))],
    }
    result = await _run_extract(rows, bindings)
    assert "F2-1-gross-raw-materials-opening" in result
    entry = result["F2-1-gross-raw-materials-opening"]
    assert entry["value"] == pytest.approx(100000.0)
    assert entry["column"] == "期初余额"
    assert entry["is_abs"] is False
    assert entry["account"] == "1401"


# ---------------------------------------------------------------------------
# test_extract_multi_level_leaf_only (Property 1: 叶子防双算)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_multi_level_leaf_only():
    """父+子科目时只汇总叶子，不含父级防双算."""
    bindings = [
        {"anchor": "F2-1-gross-raw-materials-opening", "expression": "TB('1401','期初余额')"},
    ]
    # 父 1401 期初 300000, 子 1401.01=100000, 1401.02=200000
    # 父是子的汇总，只取叶子=300000 (来自子), 不是 600000 (父+子)
    rows = {
        "1401": [
            TbRow("1401", Decimal("300000"), Decimal("350000"),
                  Decimal("50000"), Decimal("0")),
            TbRow("1401.01", Decimal("100000"), Decimal("150000"),
                  Decimal("30000"), Decimal("0")),
            TbRow("1401.02", Decimal("200000"), Decimal("200000"),
                  Decimal("20000"), Decimal("0")),
        ],
    }
    result = await _run_extract(rows, bindings)
    entry = result["F2-1-gross-raw-materials-opening"]
    # 只汇总叶子: 100000 + 200000 = 300000, 不含父级
    assert entry["value"] == pytest.approx(300000.0)
    assert set(entry["source_codes"]) == {"1401.01", "1401.02"}


# ---------------------------------------------------------------------------
# test_extract_impairment_abs (Property 3: 跌价 abs)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_impairment_abs():
    """跌价 1471 期初取 abs."""
    bindings = [
        {"anchor": "F2-1-impairment-impairment-provision-opening",
         "expression": "ABS(TB('1471','期初余额'))"},
    ]
    # 备抵科目贷方存负数
    rows = {
        "1471": [TbRow("1471", Decimal("-50000"), Decimal("-60000"),
                       Decimal("5000"), Decimal("15000"))],
    }
    result = await _run_extract(rows, bindings)
    entry = result["F2-1-impairment-impairment-provision-opening"]
    assert entry["value"] == pytest.approx(50000.0)
    assert entry["is_abs"] is True


# ---------------------------------------------------------------------------
# test_extract_skips_zero (Property 5: 全零跳过)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_skips_zero():
    """金额为零的 binding 不产出."""
    bindings = [
        {"anchor": "F2-1-gross-raw-materials-opening", "expression": "TB('1401','期初余额')"},
    ]
    rows = {
        "1401": [TbRow("1401", Decimal("0"), Decimal("0"),
                       Decimal("0"), Decimal("0"))],
    }
    result = await _run_extract(rows, bindings)
    assert result == {}


# ---------------------------------------------------------------------------
# test_extract_empty_graceful
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_empty_graceful():
    """缺 year/project_id → 优雅返回 {}."""
    import uuid
    ctx = types.SimpleNamespace(db=None, project_id=None, year=None)
    result = await extract_f2_category_values(ctx, [{"anchor": "x", "expression": "TB('1401','期初余额')"}])
    assert result == {}


# ---------------------------------------------------------------------------
# test_extract_formula_driven (Property 8: 改 binding expression 改值)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_formula_driven():
    """改 binding 中的 expression 改变取值列."""
    # 同一 account 取不同列
    bindings = [
        {"anchor": "A", "expression": "TB('1401','期初余额')"},
        {"anchor": "B", "expression": "TB('1401','期末余额')"},
    ]
    rows = {
        "1401": [TbRow("1401", Decimal("100"), Decimal("200"),
                       Decimal("80"), Decimal("20"))],
    }
    result = await _run_extract(rows, bindings)
    assert result["A"]["value"] == pytest.approx(100.0)
    assert result["B"]["value"] == pytest.approx(200.0)


# ---------------------------------------------------------------------------
# test_extract_idempotent (Property 12: 同输入同输出)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_idempotent():
    """同输入两次调用产出完全相同."""
    bindings = [
        {"anchor": "F2-1-gross-raw-materials-opening", "expression": "TB('1401','期初余额')"},
    ]
    rows = {
        "1401": [TbRow("1401", Decimal("55555"), Decimal("66666"),
                       Decimal("10000"), Decimal("5000"))],
    }
    result1 = await _run_extract(rows, bindings)
    result2 = await _run_extract(rows, bindings)
    assert result1 == result2


# ---------------------------------------------------------------------------
# test_build_default_bindings_count (== 39)
# ---------------------------------------------------------------------------


def test_build_default_bindings_count():
    """默认绑定恰好 39 条: 12 原值×3 + 1 跌价×3."""
    bindings = build_default_bindings()
    assert len(bindings) == 39


# ---------------------------------------------------------------------------
# test_build_default_bindings_impairment_abs
# ---------------------------------------------------------------------------


def test_build_default_bindings_impairment_abs():
    """跌价 1471 的 opening 绑定是 ABS(TB(...))."""
    bindings = build_default_bindings()
    impairment_opening = [
        b for b in bindings
        if b["anchor"] == "F2-1-impairment-impairment-provision-opening"
    ]
    assert len(impairment_opening) == 1
    expr = impairment_opening[0]["expression"]
    assert expr.startswith("ABS(")
    assert "1471" in expr
    assert "期初余额" in expr
