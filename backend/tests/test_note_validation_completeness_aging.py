"""Wave 1 — 完整性(_execute_completeness) + 账龄衔接(_execute_aging_progression) 三态测试.

Spec:   .kiro/specs/disclosure-note-validation-completion/ Wave 1 Task 3 + Task 4
Reqs:   2.1-2.4 / 3.1-3.4 / 8.1, 8.2
属性:   Task3 → P3(漏披露出 finding) / P4(缺 TB skip) / P10(只读)
        Task4 → P5(分桶合计≠总额出 finding) / P6(期初≠上年期末出 finding，无上年 skip)

审计铁律：executor 只读不写；Skip 优于误报（缺数据 passed=True + details.skipped）；
容差走 _resolve_tolerance 不硬编码。构造 ValidationContext/ValidationRule 直接调 executor。
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
)
from app.services.note_validation_executors import (
    _execute_aging_progression,
    _execute_completeness,
)


def _rule(rtype: ValidationType, section: str = "五、1", **md) -> ValidationRule:
    return ValidationRule(
        section_code=section,
        rule_type=rtype,
        expression=f"test:{rtype.value}",
        metadata=md,
    )


def _snapshot(ctx: ValidationContext) -> dict:
    """深拷贝执行前后可比对的读源，用于只读断言（P10）。"""
    return {
        "note_data": copy.deepcopy(ctx.note_data),
        "tb_data": copy.deepcopy(ctx.tb_data),
        "prior_note_data": copy.deepcopy(ctx.prior_note_data),
    }


# ===========================================================================
# Task 3 — _execute_completeness
# ===========================================================================


class TestCompletenessSkipOnMissing:
    """P4：缺 TB 数据 → Skip_On_Missing（passed=True + details.skipped）。"""

    def test_empty_tb_data_skips(self):
        ctx = ValidationContext(note_data={}, tb_data={})
        res = _execute_completeness(_rule(ValidationType.COMPLETENESS), ctx)
        assert res.passed is True
        assert res.details.get("skipped") is True

    def test_all_zero_tb_data_skips(self):
        ctx = ValidationContext(
            note_data={},
            tb_data={"1122": Decimal("0"), "2202": Decimal("0")},
        )
        res = _execute_completeness(_rule(ValidationType.COMPLETENESS), ctx)
        assert res.passed is True
        assert res.details.get("skipped") is True

    def test_section_not_in_mapping_skips(self):
        """章节不在应披露映射内 → skip（不臆造映射）。"""
        ctx = ValidationContext(
            note_data={},
            tb_data={"1001": Decimal("500")},
        )
        # "五、99" 不在 DEFAULT_WP_MAPPING 内
        res = _execute_completeness(_rule(ValidationType.COMPLETENESS, section="五、99"), ctx)
        assert res.passed is True
        assert res.details.get("skipped") is True


class TestCompletenessFinding:
    """P3：有 TB 审定余额非零且映射章节缺失/全空 → finding。"""

    def test_missing_section_produces_finding(self):
        """章节缺失（note_data 无该 section）→ finding。"""
        ctx = ValidationContext(
            note_data={},  # 五、1 缺失
            tb_data={"1001": Decimal("12345.67")},
        )
        res = _execute_completeness(_rule(ValidationType.COMPLETENESS, section="五、1"), ctx)
        assert res.passed is False
        assert res.details.get("missing_sections")
        assert any(m["expected_section"] == "五、1" for m in res.details["missing_sections"])

    def test_empty_section_produces_finding(self):
        """章节存在但表格/正文皆空 → finding。"""
        ctx = ValidationContext(
            note_data={"五、1": {"rows": [], "total": 0, "text_content": ""}},
            tb_data={"1001": Decimal("999")},
        )
        res = _execute_completeness(_rule(ValidationType.COMPLETENESS, section="五、1"), ctx)
        assert res.passed is False
        assert res.details.get("missing_sections")


class TestCompletenessPass:
    """映射章节非空 → pass。"""

    def test_disclosed_section_passes(self):
        ctx = ValidationContext(
            note_data={"五、1": {"rows": [{"label": "库存现金", "amount": 500}], "total": 500}},
            tb_data={"1001": Decimal("500")},
        )
        res = _execute_completeness(_rule(ValidationType.COMPLETENESS, section="五、1"), ctx)
        assert res.passed is True
        assert not res.details.get("missing_sections")

    def test_text_only_section_passes(self):
        ctx = ValidationContext(
            note_data={"五、1": {"rows": [], "text_content": "货币资金主要为银行存款"}},
            tb_data={"1001": Decimal("500")},
        )
        res = _execute_completeness(_rule(ValidationType.COMPLETENESS, section="五、1"), ctx)
        assert res.passed is True


class TestCompletenessReadOnly:
    """P10：执行前后 ctx 读源深比不变（只读，不写 DB/ctx）。"""

    def test_finding_path_read_only(self):
        ctx = ValidationContext(
            note_data={"五、1": {"rows": [], "total": 0}},
            tb_data={"1001": Decimal("999")},
        )
        before = _snapshot(ctx)
        _execute_completeness(_rule(ValidationType.COMPLETENESS, section="五、1"), ctx)
        after = _snapshot(ctx)
        assert before == after

    def test_skip_path_read_only(self):
        ctx = ValidationContext(note_data={}, tb_data={})
        before = _snapshot(ctx)
        _execute_completeness(_rule(ValidationType.COMPLETENESS), ctx)
        after = _snapshot(ctx)
        assert before == after


# ===========================================================================
# Task 4 — _execute_aging_progression
# ===========================================================================


def _aging_table(*value_rows, headers=None):
    """构造账龄表 table_data（headers + rows[].values 位置值）。"""
    if headers is None:
        headers = ["项目", "1年以内", "1-2年", "2-3年", "合计"]
    rows = [{"label": lbl, "values": vals} for lbl, vals in value_rows]
    return {"headers": headers, "rows": rows}


class TestAgingSkipOnMissing:
    def test_no_table_skips(self):
        ctx = ValidationContext(note_data={})
        res = _execute_aging_progression(_rule(ValidationType.AGING_PROGRESSION), ctx)
        assert res.passed is True
        assert res.details.get("skipped") is True

    def test_no_aging_columns_skips(self):
        ctx = ValidationContext(
            note_data={"五、1": {"headers": ["项目", "金额"], "rows": [
                {"label": "甲", "values": ["甲", 100]},
            ]}}
        )
        res = _execute_aging_progression(_rule(ValidationType.AGING_PROGRESSION), ctx)
        assert res.passed is True
        assert res.details.get("skipped") is True


class TestAgingBucketSum:
    """P5：Σ账龄分桶 = 总额。"""

    def test_balanced_buckets_pass(self):
        ctx = ValidationContext(
            note_data={"五、1": _aging_table(("应收账款", ["应收账款", 100, 50, 30, 180]))}
        )
        res = _execute_aging_progression(_rule(ValidationType.AGING_PROGRESSION), ctx)
        assert res.passed is True
        assert res.details.get("unbalanced_rows") == []

    def test_unbalanced_buckets_finding(self):
        ctx = ValidationContext(
            note_data={"五、1": _aging_table(("应收账款", ["应收账款", 100, 50, 30, 999]))}
        )
        res = _execute_aging_progression(_rule(ValidationType.AGING_PROGRESSION), ctx)
        assert res.passed is False
        assert len(res.details.get("unbalanced_rows", [])) == 1
        assert res.diff_amount is not None and res.diff_amount > 0


class TestAgingContinuity:
    """P6：本年期初 = 上年期末；无上年数据则该子校验 skip。"""

    def _current(self):
        headers = ["项目", "期初", "1年以内", "1-2年", "合计"]
        # 期初=50，桶 30+20=50=合计 → 桶合计平衡
        return {
            "headers": headers,
            "rows": [{"label": "甲", "values": ["甲", 50, 30, 20, 50]}],
        }

    def _prior(self, closing):
        return {
            "headers": ["项目", "期末", "1年以内", "合计"],
            "rows": [{"label": "甲", "values": ["甲", closing, 0, closing]}],
        }

    def test_opening_ne_prior_closing_finding(self):
        ctx = ValidationContext(
            note_data={"五、1": self._current()},
            prior_note_data={"五、1": self._prior(60)},  # 上年期末 60 ≠ 本年期初 50
        )
        res = _execute_aging_progression(_rule(ValidationType.AGING_PROGRESSION), ctx)
        assert res.passed is False
        assert res.details.get("continuity_checked") is True
        assert len(res.details.get("continuity_issues", [])) == 1

    def test_opening_eq_prior_closing_pass(self):
        ctx = ValidationContext(
            note_data={"五、1": self._current()},
            prior_note_data={"五、1": self._prior(50)},  # 上年期末 50 == 本年期初 50
        )
        res = _execute_aging_progression(_rule(ValidationType.AGING_PROGRESSION), ctx)
        assert res.passed is True
        assert res.details.get("continuity_checked") is True
        assert res.details.get("continuity_issues") == []

    def test_no_prior_skips_continuity(self):
        ctx = ValidationContext(note_data={"五、1": self._current()}, prior_note_data={})
        res = _execute_aging_progression(_rule(ValidationType.AGING_PROGRESSION), ctx)
        assert res.passed is True  # 桶平衡 + 衔接子校验 skip
        assert res.details.get("continuity_checked") is False


class TestAgingReadOnly:
    """P10：执行前后 ctx 读源深比不变。"""

    def test_read_only_on_finding(self):
        ctx = ValidationContext(
            note_data={"五、1": _aging_table(("应收账款", ["应收账款", 100, 50, 30, 999]))},
            prior_note_data={},
        )
        before = _snapshot(ctx)
        _execute_aging_progression(_rule(ValidationType.AGING_PROGRESSION), ctx)
        after = _snapshot(ctx)
        assert before == after


# ===========================================================================
# PBT（fast profile: max_examples=5）
# ===========================================================================


class TestCompletenessProperty:
    @settings(max_examples=5)
    @given(bal=st.integers(min_value=1, max_value=10_000_000))
    def test_nonzero_balance_empty_mapped_section_always_finding(self, bal):
        """P3 属性：任意非零 TB 余额 + 映射章节全空 → 恒 finding。"""
        ctx = ValidationContext(
            note_data={"五、1": {"rows": [], "total": 0}},
            tb_data={"1001": Decimal(str(bal))},
        )
        res = _execute_completeness(_rule(ValidationType.COMPLETENESS, section="五、1"), ctx)
        assert res.passed is False


class TestAgingBucketProperty:
    @settings(max_examples=5)
    @given(
        a=st.integers(min_value=0, max_value=1_000_000),
        b=st.integers(min_value=0, max_value=1_000_000),
        c=st.integers(min_value=0, max_value=1_000_000),
    )
    def test_bucket_sum_equals_total_always_pass(self, a, b, c):
        """P5 属性：桶合计恒等于总额时 → 恒 pass（容差内）。"""
        ctx = ValidationContext(
            note_data={"五、1": _aging_table(("行", ["行", a, b, c, a + b + c]))}
        )
        res = _execute_aging_progression(_rule(ValidationType.AGING_PROGRESSION), ctx)
        assert res.passed is True
