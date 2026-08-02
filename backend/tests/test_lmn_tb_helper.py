"""_lmn_tb_helper 守卫测试.

覆盖：
- Property 1: 叶子聚合守恒（负债类 closing 取值 + 防父子双算 + 点号边界）
- Property 3: 损益类取 `trial_balance` 本期发生额，**不用 `debit - credit`**
- Property 4: 灰度 OFF 全 0 / DB 异常 fail-open
- get_active_filter 统一口径调用

🔴 **本文件三条断言曾锁定错误行为，已按 spec Requirement 11.4 诚实改写**：

1. ``test_fetch_income_direction_debit_minus_credit`` 原断言
   ``end_balance == 8000 - 3000`` —— 而含年末结转损益的账套上 ``debit == credit``
   恒成立（DB 实证 ``6603`` 及每个子科目双侧均为 543,020,073.49），该口径产出恒 0。
   现改为断言取 ``trial_balance`` 本期发生额，并新增
   ``test_income_carryforward_ledger_would_be_zero_under_old_formula`` 作反证。

2. ``test_leaf_aggregation_no_double_count`` 原直接 import 已删除的 ``_is_leaf``，
   且用 ``2001``/``200101``/``200102`` **无点号平铺**码，隐含「``startswith`` 即父子」
   假设。现改为委托共享件 ``select_leaves`` 的点号边界语义，并新增
   ``test_dot_boundary_rejects_flat_sibling_code`` 作反证（旧实现必红）。

spec: .kiro/specs/l-cycle-four-table-extraction-and-disclosure-alignment/
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import sqlalchemy as sa

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(project_id="proj-001", year=2025):
    """构造最小 RenderContext 替身。"""
    ctx = SimpleNamespace()
    ctx.db = MagicMock()
    ctx.db.execute = AsyncMock()
    ctx.project_id = project_id
    ctx.year = year
    return ctx


def _tb_row(
    account_code="2001",
    account_name="",
    opening_balance=0,
    closing_balance=0,
    debit_amount=0,
    credit_amount=0,
    closing_direction="credit",
    dataset_id="ds-1",
):
    """`tb_balance` 行替身（列名与生产 SELECT 一致）。"""
    return SimpleNamespace(
        account_code=account_code,
        account_name=account_name,
        opening_balance=opening_balance,
        closing_balance=closing_balance,
        debit_amount=debit_amount,
        credit_amount=credit_amount,
        closing_direction=closing_direction,
        dataset_id=dataset_id,
    )


def _trial_row(standard_account_code="6603", unadjusted_amount=0, opening_balance=0):
    """`trial_balance` 行替身。"""
    return SimpleNamespace(
        standard_account_code=standard_account_code,
        unadjusted_amount=unadjusted_amount,
        opening_balance=opening_balance,
    )


def _enable(monkeypatch, *, enabled=True):
    monkeypatch.setattr(
        "app.routers.wp_render_strategies._lmn_tb_helper.settings",
        SimpleNamespace(LMN_FOUR_TABLE_EXTRACTION_ENABLED=enabled),
    )
    monkeypatch.setattr(
        "app.routers.wp_render_strategies._lmn_tb_helper.get_active_filter",
        AsyncMock(return_value=sa.true()),
    )


def _dispatch_by_table(*, trial_rows=None, tb_rows=None):
    """按 SQL 文本区分 `trial_balance` / `tb_balance` 两次查询的替身。

    🔴 替身不区分表就会让「trial_balance 优先」与「tb_balance 兜底」两条路径
    返回同一批行，把守卫变成噪声。
    """

    async def _execute(stmt):
        sql = str(stmt).lower()
        result = MagicMock()
        if "trial_balance" in sql:
            result.fetchall.return_value = list(trial_rows or [])
        else:
            result.fetchall.return_value = list(tb_rows or [])
        return result

    return _execute


# ---------------------------------------------------------------------------
# Property 1: 负债类取值与叶子聚合
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_balance_exact_code_returns_closing(monkeypatch):
    """精确码命中时直接取该行余额，不再下钻叶子。"""
    _enable(monkeypatch)
    from app.routers.wp_render_strategies._lmn_tb_helper import fetch_tb_for_balance

    ctx = _make_ctx()
    ctx.db.execute = _dispatch_by_table(
        tb_rows=[
            _tb_row(
                account_code="2001",
                opening_balance=1000,
                closing_balance=5000,
                debit_amount=2000,
                credit_amount=1500,
            )
        ]
    )

    result = await fetch_tb_for_balance(ctx, "2001")

    assert result["end_balance"] == 5000
    assert result["begin_balance"] == 1000
    assert result["debit_amount"] == 2000
    assert result["credit_amount"] == 1500
    assert result["account_code"] == "2001"


@pytest.mark.asyncio
async def test_leaf_aggregation_no_double_count(monkeypatch):
    """父科目行无金额时按叶子聚合，父行不参与求和（Property 1）。"""
    _enable(monkeypatch)
    from app.routers.wp_render_strategies._lmn_tb_helper import fetch_tb_for_balance

    ctx = _make_ctx()
    # 父行存在但**不在** codes 精确集合内（用 2501 查，父行是 2501 → 会命中精确分支），
    # 故这里用子科目场景：查 2701，父行 2701 无金额但存在 → 精确分支返回 0。
    # 为测叶子聚合，构造「父行不存在、只有子行」的参差树。
    ctx.db.execute = _dispatch_by_table(
        tb_rows=[
            _tb_row(account_code="2701.01", opening_balance=600, closing_balance=600,
                    debit_amount=300, credit_amount=200),
            _tb_row(account_code="2701.02", opening_balance=400, closing_balance=400,
                    debit_amount=200, credit_amount=300),
            # 非叶子中间层 + 其两个叶子孙科目（验证只取最明细且不重复计父）
            _tb_row(account_code="2701.03", opening_balance=999, closing_balance=999),
            _tb_row(account_code="2701.03.01", opening_balance=100, closing_balance=100),
            _tb_row(account_code="2701.03.02", opening_balance=50, closing_balance=50),
        ]
    )

    result = await fetch_tb_for_balance(ctx, "2701")

    # 叶子 = 2701.01 + 2701.02 + 2701.03.01 + 2701.03.02
    assert result["end_balance"] == 600 + 400 + 100 + 50
    assert result["begin_balance"] == 600 + 400 + 100 + 50
    # 中间层 2701.03 的 999 不得计入
    assert result["end_balance"] != 600 + 400 + 999


@pytest.mark.asyncio
async def test_dot_boundary_rejects_flat_sibling_code(monkeypatch):
    """点号边界：``2231`` 不得把同级平铺码 ``22310`` 当成自己的子科目。

    🔴 旧实现 ``_is_leaf`` 用 ``other.startswith(code)`` 判定 → ``22310`` 会被当成
    ``2231`` 的子科目，使父行被判为非叶子而整支金额丢失。本用例在旧实现下必红。
    """
    _enable(monkeypatch)
    from app.routers.wp_render_strategies._lmn_tb_helper import fetch_tb_for_balance

    ctx = _make_ctx()
    ctx.db.execute = _dispatch_by_table(
        tb_rows=[
            _tb_row(account_code="2231", opening_balance=0, closing_balance=700),
            # 平铺同级码（LIKE '2231%' 会一并捞出，但它不是 2231 的子科目）
            _tb_row(account_code="22310", opening_balance=0, closing_balance=12345),
        ]
    )

    result = await fetch_tb_for_balance(ctx, "2231")

    # 精确码 2231 命中 → 直接取 700，不受 22310 干扰
    assert result["end_balance"] == 700


# ---------------------------------------------------------------------------
# Property 3: 损益类取本期发生额
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_income_uses_trial_balance_occurrence(monkeypatch):
    """损益类优先取 `trial_balance.unadjusted_amount`（本期发生额权威口径）。"""
    _enable(monkeypatch)
    from app.routers.wp_render_strategies._lmn_tb_helper import (
        SOURCE_TRIAL_BALANCE,
        fetch_tb_for_income,
    )

    ctx = _make_ctx()
    ctx.db.execute = _dispatch_by_table(
        trial_rows=[
            _trial_row(standard_account_code="6603", unadjusted_amount=171005147.56)
        ],
        # 结转损益导致 tb_balance 双侧相等 —— 若走旧口径会得 0
        tb_rows=[
            _tb_row(
                account_code="6603",
                debit_amount=543020073.49,
                credit_amount=543020073.49,
            )
        ],
    )

    result = await fetch_tb_for_income(ctx, "6603")

    assert result["end_balance"] == pytest.approx(171005147.56)
    assert result["occurrence"] == pytest.approx(171005147.56)
    assert result["source"] == SOURCE_TRIAL_BALANCE


@pytest.mark.asyncio
async def test_income_carryforward_would_be_zero_under_old_formula(monkeypatch):
    """反证：结转损益账套下旧口径 ``debit - credit`` 恒 0，新口径非零。

    🔴 DB 实证 ``6603`` 及**每一个**子科目 ``debit == credit``（543,020,073.49）。
    本用例断言新实现不返回 0 —— 在旧实现下必红。
    """
    _enable(monkeypatch)
    from app.routers.wp_render_strategies._lmn_tb_helper import (
        SOURCE_TB_BALANCE_DEBIT,
        fetch_tb_for_income,
    )

    ctx = _make_ctx()
    # trial_balance 无该行 → 走 tb_balance 借方兜底
    ctx.db.execute = _dispatch_by_table(
        trial_rows=[],
        tb_rows=[
            _tb_row(
                account_code="6603",
                debit_amount=543020073.49,
                credit_amount=543020073.49,
            )
        ],
    )

    result = await fetch_tb_for_income(ctx, "6603")

    old_formula_value = 543020073.49 - 543020073.49
    assert old_formula_value == 0  # 旧口径恒 0（本行即缺陷复现）
    assert result["end_balance"] == pytest.approx(543020073.49)
    assert result["end_balance"] != old_formula_value
    assert result["source"] == SOURCE_TB_BALANCE_DEBIT


# ---------------------------------------------------------------------------
# Property 4: 灰度 OFF / fail-open
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grayscale_off_returns_zero(monkeypatch):
    """灰度关闭时全 0 且不查库（Property 4 逐字节等价）。"""
    _enable(monkeypatch, enabled=False)
    from app.routers.wp_render_strategies._lmn_tb_helper import (
        fetch_tb_for_balance,
        fetch_tb_for_income,
    )

    ctx = _make_ctx()

    balance_result = await fetch_tb_for_balance(ctx, "2001")
    assert balance_result["begin_balance"] == 0
    assert balance_result["end_balance"] == 0
    assert balance_result["debit_amount"] == 0
    assert balance_result["credit_amount"] == 0
    assert balance_result["account_code"] == "2001"

    income_result = await fetch_tb_for_income(ctx, "6603")
    assert income_result["begin_balance"] == 0
    assert income_result["end_balance"] == 0
    assert income_result["debit_amount"] == 0
    assert income_result["credit_amount"] == 0
    assert income_result["account_code"] == "6603"

    ctx.db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_db_exception_failopen(monkeypatch):
    """DB 异常返回零值且不抛（Property 4）。"""
    _enable(monkeypatch)
    from app.routers.wp_render_strategies._lmn_tb_helper import (
        fetch_tb_for_balance,
        fetch_tb_for_income,
    )

    ctx = _make_ctx()
    ctx.db.execute = AsyncMock(side_effect=Exception("DB down"))

    balance_result = await fetch_tb_for_balance(ctx, "2001")
    assert balance_result["end_balance"] == 0
    assert balance_result["begin_balance"] == 0
    assert balance_result["account_code"] == "2001"

    income_result = await fetch_tb_for_income(ctx, "6603")
    assert income_result["end_balance"] == 0
    assert income_result["debit_amount"] == 0
    assert income_result["account_code"] == "6603"


# ---------------------------------------------------------------------------
# 入参归一 + get_active_filter 口径
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_accepts_code_sequence(monkeypatch):
    """入参支持科目码集合（报表行可解析出多个标准码）。"""
    _enable(monkeypatch)
    from app.routers.wp_render_strategies._lmn_tb_helper import fetch_tb_for_balance

    ctx = _make_ctx()
    ctx.db.execute = _dispatch_by_table(
        tb_rows=[
            _tb_row(account_code="2501", closing_balance=300),
            _tb_row(account_code="2502", closing_balance=200),
        ]
    )

    result = await fetch_tb_for_balance(ctx, ["2501", "2502"])

    assert result["end_balance"] == 500
    assert result["account_code"] == "2501/2502"


@pytest.mark.asyncio
async def test_get_active_filter_called_with_platform_signature(monkeypatch):
    """四表查询走统一 `get_active_filter`（禁裸写 is_deleted）。"""
    mock_filter = AsyncMock(return_value=sa.true())
    monkeypatch.setattr(
        "app.routers.wp_render_strategies._lmn_tb_helper.settings",
        SimpleNamespace(LMN_FOUR_TABLE_EXTRACTION_ENABLED=True),
    )
    monkeypatch.setattr(
        "app.routers.wp_render_strategies._lmn_tb_helper.get_active_filter",
        mock_filter,
    )

    from app.models.audit_platform_models import TbBalance
    from app.routers.wp_render_strategies._lmn_tb_helper import fetch_tb_for_balance

    ctx = _make_ctx(project_id="proj-002", year=2025)
    ctx.db.execute = _dispatch_by_table(tb_rows=[])

    await fetch_tb_for_balance(ctx, "2001")

    mock_filter.assert_called_once_with(ctx.db, TbBalance.__table__, "proj-002", 2025)


@pytest.mark.asyncio
async def test_empty_codes_returns_zero_without_query(monkeypatch):
    """空科目码集合（L7 宁缺勿造）不查库、返回零值。"""
    _enable(monkeypatch)
    from app.routers.wp_render_strategies._lmn_tb_helper import fetch_tb_for_balance

    ctx = _make_ctx()
    result = await fetch_tb_for_balance(ctx, [])

    assert result["end_balance"] == 0
    assert result["account_code"] == ""
    ctx.db.execute.assert_not_called()
