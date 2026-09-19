"""单元测试：四表库叶子源只读守卫 + 取数契约纯逻辑（Task 2.3）。

DB 相关的 tb_value/prev_value/aux_value 查询在集成测试中覆盖；此处聚焦：
- is_four_table_target 识别四表库地址（多形态）
- guard_four_table_leaf_readonly 仅拒绝 auto_calc 回填四表库
- _signed_v1 借正贷负（Req 12.3）
- _normalize_column / _is_pnl 取数分派前置逻辑（Req 12.4）
- execute_formula 执行期兜底：auto_calc 目标为四表库 → 跳过回填不改值

Requirements: 12.1, 12.2, 12.3, 12.4, 12.5
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.formula_engine import FormulaContext
from app.services.formula_management.engine import FormulaRecord, execute_formula
from app.services.formula_management import four_table_source as fts
from app.services.formula_management.four_table_source import (
    FourTableReadonlyError,
    guard_four_table_leaf_readonly,
    is_four_table_target,
)


# ─────────────────────── is_four_table_target ───────────────────────
@pytest.mark.parametrize(
    "target",
    [
        "trial_balance/1001/审定数",
        "tb_balance:1001",
        "tb_ledger",
        "tb_aux_balance/6001/客户",
        "tb://1001#审定数",
        "aux://1122#客户",
        "TB('1001','期末余额')",
        "PREV('1001','期末余额')",
        "AUX('1122','客户')",
        "SUM_TB('1001~1099','审定数')",
        "TB:1001",
        "aux:1122",
    ],
)
def test_is_four_table_target_positive(target):
    assert is_four_table_target(target) is True


@pytest.mark.parametrize(
    "target",
    [
        "",
        None,
        "WP('D2','明细表D2-2','E100')",
        "report/BS/1",
        "note:五、3",
        "C1",
        "ROW('IS-019')",
    ],
)
def test_is_four_table_target_negative(target):
    assert is_four_table_target(target) is False


# ─────────────────────── guard_four_table_leaf_readonly ───────────────────────
def test_guard_rejects_auto_calc_on_four_table():
    with pytest.raises(FourTableReadonlyError):
        guard_four_table_leaf_readonly(
            formula_type="auto_calc", target="tb://1001#审定数"
        )


def test_guard_allows_logic_check_and_reasonability_on_four_table():
    # logic_check / reasonability 不改值，可引用四表库地址，不受守卫限制。
    guard_four_table_leaf_readonly(formula_type="logic_check", target="TB('1001')")
    guard_four_table_leaf_readonly(formula_type="reasonability", target="tb_balance:1001")


def test_guard_allows_auto_calc_on_non_four_table():
    # 底稿/报表单元可正常定义 auto_calc 回填公式。
    guard_four_table_leaf_readonly(formula_type="auto_calc", target="report/BS/1")
    guard_four_table_leaf_readonly(formula_type="auto_calc", target="WP('D2','s','E1')")


# ─────────────────────── _signed_v1（借正贷负，Req 12.3）───────────────────────
def test_signed_v1_prefers_debit_minus_credit():
    # 备抵类（如累计折旧）贷方余额：debit=0 credit=500 → -500，方向不失真。
    assert fts._signed_v1(Decimal("0"), Decimal("500"), None) == Decimal("-500")
    # 借方科目：debit=800 credit=0 → +800
    assert fts._signed_v1(Decimal("800"), Decimal("0"), None) == Decimal("800")


def test_signed_v1_falls_back_to_balance_when_no_debit_credit():
    # 无借贷发生额列 → 回退余额列（已按 v1 借正贷负口径）。
    assert fts._signed_v1(None, None, Decimal("-300")) == Decimal("-300")
    assert fts._signed_v1(None, None, None) == Decimal("0")


# ─────────────────────── _normalize_column / _is_pnl（Req 12.4）───────────────────────
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("期末余额", "closing"),
        ("审定数", "closing"),
        ("年初余额", "opening"),
        ("期初余额", "opening"),
        ("本期发生额", "period"),
        ("发生额", "period"),
        ("", "closing"),
        (None, "closing"),
    ],
)
def test_normalize_column(raw, expected):
    assert fts._normalize_column(raw) == expected


@pytest.mark.parametrize(
    "code,is_pnl",
    [
        ("6001", True),   # 主营业务收入
        ("5001", True),   # 生产成本
        ("6401", True),   # 主营业务成本
        ("1001", False),  # 库存现金（资产）
        ("2202", False),  # 应付账款（负债）
        ("4001", False),  # 实收资本（权益）
        ("", False),
    ],
)
def test_is_pnl(code, is_pnl):
    assert fts._is_pnl(code) is is_pnl


# ─────────────────────── execute_formula 执行期兜底（Req 12.2）───────────────────────
@pytest.mark.asyncio
async def test_execute_auto_calc_on_four_table_skips_backfill_no_mutation():
    ctx = FormulaContext(row_cache={"r1": Decimal("100")})
    before = dict(ctx.row_cache)
    applied: dict[str, Decimal] = {}
    f = FormulaRecord(
        id="f-ft",
        formula_type="auto_calc",
        target_cell="tb://1001#审定数",  # 目标为四表库单元
        expression="ROW('r1')",
    )
    res = await execute_formula(
        None,
        formula=f,
        ctx=ctx,
        apply_value=lambda c, v: applied.__setitem__(c, v),
        resolve_refs=False,
    )
    assert res.errors  # 记描述性错误
    assert res.updated_cells == []  # 未回填
    assert res.values == {}
    assert res.last_computed_at is None  # 不写时间戳
    assert applied == {}  # 未调用回填回调
    assert ctx.row_cache == before  # 绝不改值
