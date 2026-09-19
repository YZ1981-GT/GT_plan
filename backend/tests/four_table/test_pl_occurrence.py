"""损益类发生额取数共享件的纯函数单测。

核心是钉死「**禁止** `debit - credit`」—— 该表达式在含年末结转损益的全年账上
结构性恒零（活体项目 `005a6f2d` 的 `6601` 及其 40+ 子科目逐行 `debit == credit`）。

spec: .kiro/specs/k-cycle-four-table-extraction-and-disclosure-completion/
      Property 5, 6, 7
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.four_table.leaf_aggregation import LeafRow
from app.services.four_table.pl_occurrence import (
    SOURCE_NONE,
    SOURCE_TB_BALANCE,
    SOURCE_TRIAL_BALANCE,
    AccountNature,
    PlOccurrence,
    build_occurrence_prefill,
    normalize_for_report,
    pick_occurrence,
    sum_leaf_occurrence,
    sum_longest_prefix_only,
)

#: 金额域有界生成器 —— `st.floats()` 默认会生成 ±inf 让断言变 NaN（D1 踩过）
_AMOUNT = st.floats(
    min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False, width=32
)


# ─────────────────────────────────────────────────────────────────────────────
# pick_occurrence
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("debit", "credit", "nature", "expected"),
    [
        # 费用类取借方
        (163042014.46, 163042014.46, AccountNature.EXPENSE, 163042014.46),
        (100.0, 0.0, AccountNature.EXPENSE, 100.0),
        (0.0, 100.0, AccountNature.EXPENSE, 0.0),
        # 收益类取贷方
        (146477.91, 146477.91, AccountNature.INCOME, 146477.91),
        (0.0, 100.0, AccountNature.INCOME, 100.0),
        (100.0, 0.0, AccountNature.INCOME, 0.0),
        # 字符串形态的 nature 亦可（render 反序列化路径）
        (7.0, 3.0, "expense", 7.0),
        (7.0, 3.0, "income", 3.0),
        # 未知 nature 退化为费用类（借方），不抛错
        (7.0, 3.0, "unknown", 7.0),
    ],
)
def test_pick_occurrence_takes_direction_side(debit, credit, nature, expected):
    assert pick_occurrence(debit, credit, nature) == pytest.approx(expected)


def test_pick_occurrence_never_returns_net_difference():
    """🔴 活体实证：损益类 debit == credit，净额恒 0。

    本用例是「若有人把实现改回 `debit - credit`」的直接探针 —— 届时返回 0
    而非 163,042,014.46。
    """
    debit = credit = 163042014.46
    assert pick_occurrence(debit, credit, AccountNature.EXPENSE) == pytest.approx(debit)
    assert pick_occurrence(debit, credit, AccountNature.EXPENSE) != pytest.approx(0.0)
    # 反向自检：净额确实是 0（证明这个数据形态就是活体形态）
    assert debit - credit == pytest.approx(0.0)


@given(debit=_AMOUNT, credit=_AMOUNT)
@settings(max_examples=5)
def test_property_pick_occurrence_is_projection(debit, credit):
    """Property：pick_occurrence 恒等于两个入参之一，永不是二者的算术组合。"""
    exp = pick_occurrence(debit, credit, AccountNature.EXPENSE)
    inc = pick_occurrence(debit, credit, AccountNature.INCOME)
    assert exp == pytest.approx(debit)
    assert inc == pytest.approx(credit)


# ─────────────────────────────────────────────────────────────────────────────
# normalize_for_report
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("amount", "nature", "expected"),
    [
        # 收益类取绝对值：两种存储约定并存（实证 6117 在两个项目符号相反）
        (-146477.91, AccountNature.INCOME, 146477.91),
        (15712.56, AccountNature.INCOME, 15712.56),
        # 费用类保留符号（负值 = 合法的净冲回）
        (-12220782.48, AccountNature.EXPENSE, -12220782.48),
        (505080400.27, AccountNature.EXPENSE, 505080400.27),
        (0.0, AccountNature.INCOME, 0.0),
    ],
)
def test_normalize_for_report(amount, nature, expected):
    assert normalize_for_report(amount, nature) == pytest.approx(expected)


@given(amount=_AMOUNT)
@settings(max_examples=5)
def test_property_income_normalization_is_nonnegative(amount):
    """Property：收益类归一后恒非负；费用类归一是恒等映射。"""
    assert normalize_for_report(amount, AccountNature.INCOME) >= 0
    assert normalize_for_report(amount, AccountNature.EXPENSE) == pytest.approx(amount)


# ─────────────────────────────────────────────────────────────────────────────
# sum_longest_prefix_only（防父子双计）
# ─────────────────────────────────────────────────────────────────────────────


def test_sum_longest_prefix_only_no_double_count():
    """父码与子码并存时，每行只归属一次 —— 这是 `LIKE '2701%'` 的替代品。"""
    rows = [
        ("2801", 1000.0),
        ("2801-01", 600.0),
        ("2801-02", 400.0),
    ]
    # 只要父码：三行都归属到 '2801'（最长命中前缀就是它）→ 2000
    # 这正是历史 LIKE '2801%' 的行为，仍是双计
    assert sum_longest_prefix_only(rows, ["2801"]) == pytest.approx(2000.0)
    # 同时声明父子码：子行归属到更长的子码，父行归属父码 → 仍是全量，但归属明确
    assert sum_longest_prefix_only(rows, ["2801", "2801-01"]) == pytest.approx(2000.0)


def test_sum_longest_prefix_only_picks_most_specific():
    """同一行被多个前缀命中时归属到最长的那个（互斥归属，不重复累加）。"""
    rows = [("1231-03", 900217.36)]
    assert sum_longest_prefix_only(rows, ["1231"]) == pytest.approx(900217.36)
    assert sum_longest_prefix_only(rows, ["1231", "1231-03"]) == pytest.approx(900217.36)


@pytest.mark.parametrize("wanted", [None, [], [""], ["  "]])
def test_sum_longest_prefix_only_empty_wanted(wanted):
    """空白前缀必须与空串同样剔除 —— 否则 `startswith('')` 恒真会命中所有行。"""
    assert sum_longest_prefix_only([("6601", 1.0)], wanted) == pytest.approx(0.0)


def test_sum_longest_prefix_only_ignores_unmatched():
    rows = [("6601", 100.0), ("6602", 200.0)]
    assert sum_longest_prefix_only(rows, ["6601"]) == pytest.approx(100.0)


# ─────────────────────────────────────────────────────────────────────────────
# sum_leaf_occurrence / build_occurrence_prefill
# ─────────────────────────────────────────────────────────────────────────────


def _leaf(code: str, name: str, debit: float, credit: float) -> LeafRow:
    return LeafRow(
        account_code=code, account_name=name, debit=debit, credit=credit, dataset_id="ds1"
    )


def test_sum_leaf_occurrence_requires_dot_boundary():
    """前缀匹配须有点号边界 —— `6601` 不得命中 `66010`（不同科目）。"""
    leaves = [
        _leaf("6601.01", "销售费用_职工薪酬", 100.0, 100.0),
        _leaf("66010", "别的科目", 999.0, 999.0),
    ]
    assert sum_leaf_occurrence(leaves, ["6601"], AccountNature.EXPENSE) == pytest.approx(
        100.0
    )


def test_build_occurrence_prefill_single_amount_column():
    """损益类预填不再输出 debit/credit 双列（恒相等，双列只会误导）。"""
    leaves = [
        _leaf("6601.01", "销售费用_职工薪酬", 37189411.65, 37189411.65),
        _leaf("6601.11", "销售费用_劳务手续费", 42997579.18, 42997579.18),
    ]
    rows = build_occurrence_prefill(leaves, ["6601"], AccountNature.EXPENSE)
    assert [r["name"] for r in rows] == ["销售费用_劳务手续费", "销售费用_职工薪酬"]
    for r in rows:
        assert set(r) == {"name", "code", "unadjusted", "audited"}
        assert r["unadjusted"] == pytest.approx(r["audited"])
    assert rows[0]["unadjusted"] == pytest.approx(42997579.18)


def test_build_occurrence_prefill_skips_zero_and_unnamed():
    """宁缺勿造：无名或零金额的叶子跳过。"""
    leaves = [
        _leaf("6601.01", "", 100.0, 100.0),
        _leaf("6601.02", "销售费用_包装费", 0.0, 0.0),
        _leaf("6601.03", "销售费用_运输费", 3131075.06, 3131075.06),
    ]
    rows = build_occurrence_prefill(leaves, ["6601"], AccountNature.EXPENSE)
    assert [r["name"] for r in rows] == ["销售费用_运输费"]


def test_build_occurrence_prefill_income_normalized():
    """收益类叶子按报表口径取绝对值（两种存储约定并存）。"""
    leaves = [_leaf("6117.01", "其他收益_政府补助", 0.0, -146477.91)]
    rows = build_occurrence_prefill(leaves, ["6117"], AccountNature.INCOME)
    assert rows[0]["unadjusted"] == pytest.approx(146477.91)


def test_build_occurrence_prefill_empty_when_no_match():
    assert build_occurrence_prefill([], ["6601"], AccountNature.EXPENSE) == []


@given(
    amounts=st.lists(_AMOUNT, min_size=1, max_size=6),
)
@settings(max_examples=5)
def test_property_prefill_sum_equals_leaf_total(amounts):
    """Property 7：预填各行之和 == 叶子发生额合计（同口径，容差 0.01）。"""
    leaves = [
        _leaf(f"6601.{i:02d}", f"子科目{i}", amt, 0.0) for i, amt in enumerate(amounts, 1)
    ]
    rows = build_occurrence_prefill(leaves, ["6601"], AccountNature.EXPENSE)
    total = sum_leaf_occurrence(leaves, ["6601"], AccountNature.EXPENSE)
    # 预填跳过 |amount| < 0.005 的行，故用同样阈值过滤后比对
    expected = sum(a for a in amounts if abs(a) >= 0.005)
    assert sum(r["unadjusted"] for r in rows) == pytest.approx(expected, abs=0.01)
    assert total == pytest.approx(sum(amounts), abs=0.01)


# ─────────────────────────────────────────────────────────────────────────────
# PlOccurrence 派生属性
# ─────────────────────────────────────────────────────────────────────────────


def test_pl_occurrence_prefers_trial_balance():
    occ = PlOccurrence(
        unadjusted=505080400.27,
        audited=505080400.27,
        fallback_amount=163042014.46,
        source=SOURCE_TRIAL_BALANCE,
        nature=AccountNature.EXPENSE.value,
    )
    assert occ.effective_unadjusted == pytest.approx(505080400.27)
    assert occ.report_unadjusted == pytest.approx(505080400.27)


def test_pl_occurrence_falls_back_to_tb_balance():
    occ = PlOccurrence(
        fallback_amount=163042014.46,
        source=SOURCE_TB_BALANCE,
        nature=AccountNature.EXPENSE.value,
    )
    assert occ.effective_unadjusted == pytest.approx(163042014.46)
    assert occ.report_audited == pytest.approx(163042014.46)


def test_pl_occurrence_income_report_view_is_positive():
    occ = PlOccurrence(
        unadjusted=-146477.91,
        audited=-146477.91,
        source=SOURCE_TRIAL_BALANCE,
        raw_sign=-1,
        nature=AccountNature.INCOME.value,
    )
    assert occ.report_unadjusted == pytest.approx(146477.91)
    assert occ.report_audited == pytest.approx(146477.91)
    # 原始符号必须留证，不得静默丢弃
    assert occ.raw_sign == -1
    assert occ.unadjusted == pytest.approx(-146477.91)


def test_pl_occurrence_as_dict_exposes_report_view():
    occ = PlOccurrence(source=SOURCE_NONE, nature=AccountNature.EXPENSE.value)
    d = occ.as_dict()
    for key in ("report_unadjusted", "report_audited", "effective_unadjusted", "source"):
        assert key in d
    assert d["source"] == SOURCE_NONE
