"""交叉勾稽 / 跨科目勾稽 executor 测试（Wave 2 · Task5 + Task6）。

覆盖 `_execute_cross`（附注↔报表 / 附注↔附注，P7）与
`_execute_cross_account`（跨科目余额勾稽，P8）：pass / finding / Skip_On_Missing 三态
+ 只读不变式（执行前后 ctx 深比不变）。

纯函数直接构造 ValidationContext/ValidationRule 调 executor，无需 DB。
"""

from __future__ import annotations

import copy
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.note_validation_engine import (
    ValidationContext,
    ValidationRule,
    ValidationType,
    _resolve_tolerance,
)
from app.services.note_validation_executors import (
    _execute_cross,
    _execute_cross_account,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _cross_rule(section: str, *, metadata=None, expression: str = "") -> ValidationRule:
    return ValidationRule(
        section_code=section,
        rule_type=ValidationType.CROSS,
        expression=expression,
        metadata=metadata or {},
    )


def _cross_account_rule(section: str, *, metadata=None, expression: str = "") -> ValidationRule:
    return ValidationRule(
        section_code=section,
        rule_type=ValidationType.CROSS_ACCOUNT,
        expression=expression,
        metadata=metadata or {},
    )


def _assert_readonly(ctx: ValidationContext, fn, rule) -> None:
    """执行前后 ctx 深比不变（executor 只读，Req8.1 / P10）。"""
    before = copy.deepcopy(ctx)
    fn(rule, ctx)
    assert ctx == before


# ---------------------------------------------------------------------------
# Task5: _execute_cross（附注↔报表 / 附注↔附注，P7）
# ---------------------------------------------------------------------------

def test_cross_note_vs_report_mismatch_produces_finding():
    """附注章节合计 ≠ 报表对应行次金额（超容差）→ finding（P7）。"""
    ctx = ValidationContext(
        note_data={"五、3": {"total": 1000}},
        report_data={"BS-005": Decimal("1200")},
    )
    rule = _cross_rule("五、3", metadata={"report_row": "BS-005"})
    res = _execute_cross(rule, ctx)

    assert res.passed is False
    assert res.expected_value == Decimal("1200")
    assert res.actual_value == Decimal("1000")
    assert res.diff_amount == Decimal("200")
    assert res.details.get("skipped") is not True


def test_cross_note_vs_report_match_passes():
    """附注合计 = 报表行次金额 → pass。"""
    ctx = ValidationContext(
        note_data={"五、3": {"total": 1200}},
        report_data={"BS-005": Decimal("1200")},
    )
    rule = _cross_rule("五、3", metadata={"report_row": "BS-005"})
    res = _execute_cross(rule, ctx)
    assert res.passed is True


def test_cross_missing_report_row_skips():
    """引用的报表行次不在 report_data → Skip_On_Missing（不误报，Req4.3）。"""
    ctx = ValidationContext(
        note_data={"五、3": {"total": 1000}},
        report_data={"BS-005": Decimal("1200")},
    )
    rule = _cross_rule("五、3", metadata={"report_row": "BS-999"})
    res = _execute_cross(rule, ctx)

    assert res.passed is True
    assert res.details.get("skipped") is True


def test_cross_note_vs_note_mismatch_produces_finding():
    """附注章节 A 合计 ≠ 关联附注章节 B 合计（超容差）→ finding。"""
    ctx = ValidationContext(
        note_data={
            "五、3": {"total": 1000},
            "五、4": {"total": 800},
        },
    )
    rule = _cross_rule("五、3", metadata={"cross_section": "五、4"})
    res = _execute_cross(rule, ctx)

    assert res.passed is False
    assert res.expected_value == Decimal("800")
    assert res.actual_value == Decimal("1000")
    assert res.diff_amount == Decimal("200")


def test_cross_via_expression_report_token():
    """expression 含 REPORT('row') → 解析为附注↔报表比对。"""
    ctx = ValidationContext(
        note_data={"五、3": {"total": 1000}},
        report_data={"BS-005": Decimal("1000")},
    )
    rule = _cross_rule("五、3", expression="NOTE('五、3','合计','期末') = REPORT('BS-005','期末')")
    res = _execute_cross(rule, ctx)
    assert res.passed is True
    assert res.details.get("skipped") is not True


def test_cross_no_reference_skips():
    """无 report_row / cross_section / 可解析引用 → 不臆造勾稽 → skip。"""
    ctx = ValidationContext(note_data={"五、3": {"total": 1000}}, report_data={})
    rule = _cross_rule("五、3", metadata={}, expression="")
    res = _execute_cross(rule, ctx)
    assert res.passed is True
    assert res.details.get("skipped") is True


def test_cross_empty_section_skips():
    """本章节为空 / 无合计 → skip（不误报）。"""
    ctx = ValidationContext(
        note_data={"五、3": {}},
        report_data={"BS-005": Decimal("1200")},
    )
    rule = _cross_rule("五、3", metadata={"report_row": "BS-005"})
    res = _execute_cross(rule, ctx)
    assert res.passed is True
    assert res.details.get("skipped") is True


def test_cross_is_readonly():
    ctx = ValidationContext(
        note_data={"五、3": {"total": 1000}},
        report_data={"BS-005": Decimal("1200")},
    )
    rule = _cross_rule("五、3", metadata={"report_row": "BS-005"})
    _assert_readonly(ctx, _execute_cross, rule)


# ---------------------------------------------------------------------------
# Task6: _execute_cross_account（跨科目余额勾稽，P8）
# ---------------------------------------------------------------------------

def test_cross_account_section_vs_accounts_mismatch_produces_finding():
    """本附注章节合计 ≠ Σ引用科目 TB 余额（超容差）→ finding（P8）。"""
    ctx = ValidationContext(
        note_data={"五、8": {"total": 5000}},
        tb_data={"1122": Decimal("4000")},
    )
    rule = _cross_account_rule(
        "五、8", metadata={"left_section": "五、8", "right_accounts": ["1122"]}
    )
    res = _execute_cross_account(rule, ctx)

    assert res.passed is False
    assert res.diff_amount == Decimal("1000")
    assert res.details.get("skipped") is not True


def test_cross_account_match_passes():
    """章节合计 = Σ科目余额 → pass。"""
    ctx = ValidationContext(
        note_data={"五、8": {"total": 5000}},
        tb_data={"1122": Decimal("3000"), "1123": Decimal("2000")},
    )
    rule = _cross_account_rule(
        "五、8",
        metadata={"left_section": "五、8", "right_accounts": ["1122", "1123"]},
    )
    res = _execute_cross_account(rule, ctx)
    assert res.passed is True


def test_cross_account_missing_account_skips():
    """引用科目在 tb_data 中缺失 → Skip_On_Missing（不误报，Req5.2）。"""
    ctx = ValidationContext(
        note_data={"五、8": {"total": 5000}},
        tb_data={"1122": Decimal("4000")},
    )
    rule = _cross_account_rule(
        "五、8", metadata={"left_section": "五、8", "right_accounts": ["2202"]}
    )
    res = _execute_cross_account(rule, ctx)

    assert res.passed is True
    assert res.details.get("skipped") is True


def test_cross_account_related_party_two_sections():
    """往来对冲：两附注章节合计勾稽（关联方一致），不平 → finding。"""
    ctx = ValidationContext(
        note_data={
            "五、8": {"total": 5000},
            "六、2": {"total": 4500},
        },
    )
    rule = _cross_account_rule(
        "五、8", metadata={"left_section": "五、8", "right_sections": ["六、2"]}
    )
    res = _execute_cross_account(rule, ctx)
    assert res.passed is False
    assert res.diff_amount == Decimal("500")


def test_cross_account_no_reference_skips():
    """无任何跨科目引用信息 → 不臆造映射 → skip（Req5.3）。"""
    ctx = ValidationContext(
        note_data={"五、8": {"total": 5000}},
        tb_data={"1122": Decimal("4000")},
    )
    rule = _cross_account_rule("五、8", metadata={}, expression="")
    res = _execute_cross_account(rule, ctx)
    assert res.passed is True
    assert res.details.get("skipped") is True


def test_cross_account_is_readonly():
    ctx = ValidationContext(
        note_data={"五、8": {"total": 5000}},
        tb_data={"1122": Decimal("4000")},
    )
    rule = _cross_account_rule(
        "五、8", metadata={"left_section": "五、8", "right_accounts": ["1122"]}
    )
    _assert_readonly(ctx, _execute_cross_account, rule)


# ---------------------------------------------------------------------------
# Property-based（P7/P8 容差边界；fast profile）
# ---------------------------------------------------------------------------

@settings(max_examples=5)
@given(
    note_total=st.integers(min_value=1, max_value=10**9),
    report_amt=st.integers(min_value=0, max_value=10**9),
)
def test_cross_finding_iff_over_tolerance(note_total, report_amt):
    """P7：附注↔报表 passed 当且仅当 |diff| ≤ 动态容差。"""
    ctx = ValidationContext(
        note_data={"五、3": {"total": note_total}},
        report_data={"BS-005": Decimal(report_amt)},
    )
    rule = _cross_rule("五、3", metadata={"report_row": "BS-005"})
    res = _execute_cross(rule, ctx)

    diff = abs(Decimal(note_total) - Decimal(report_amt))
    tol = _resolve_tolerance(Decimal("0.01"), Decimal(report_amt), Decimal(note_total))
    assert res.details.get("skipped") is not True
    assert res.passed == (diff <= tol)


@settings(max_examples=5)
@given(
    section_total=st.integers(min_value=1, max_value=10**9),
    tb_amt=st.integers(min_value=0, max_value=10**9),
)
def test_cross_account_finding_iff_over_tolerance(section_total, tb_amt):
    """P8：跨科目 passed 当且仅当 |diff| ≤ 动态容差（科目存在时）。"""
    ctx = ValidationContext(
        note_data={"五、8": {"total": section_total}},
        tb_data={"1122": Decimal(tb_amt)},
    )
    rule = _cross_account_rule(
        "五、8", metadata={"left_section": "五、8", "right_accounts": ["1122"]}
    )
    res = _execute_cross_account(rule, ctx)

    diff = abs(Decimal(section_total) - Decimal(tb_amt))
    tol = _resolve_tolerance(Decimal("0.01"), Decimal(section_total), Decimal(tb_amt))
    assert res.details.get("skipped") is not True
    assert res.passed == (diff <= tol)
