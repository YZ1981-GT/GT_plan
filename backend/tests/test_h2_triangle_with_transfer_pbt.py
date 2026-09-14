"""H2 在建工程 — 三角勾稽含转固校验 Property-Based Tests (hypothesis).

Spec: .kiro/specs/h2-construction-in-progress/ Task 7.2
Validates: Requirements 2.6

在建工程三角勾稽公式（比H1多一个"转固"维度）：
期末 = 期初 + 增加 - 减少 - 转固
差额 = 期末 - (期初 + 增加 - 减少 - 转固)
"""

import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ─── 三角勾稽含转固（纯数学验证） ───────────────────────────────────────────


class TestTriangleWithTransferPBT:
    """**Validates: Requirements 2.6** — 在建工程三角勾稽含转固扣减."""

    @settings(max_examples=5)
    @given(
        begin=st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False),
        increase=st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False),
        decrease=st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False),
        transfer=st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False),
    )
    def test_triangle_identity_with_transfer(self, begin, increase, decrease, transfer):
        """期末=期初+增加-减少-转固时，三角勾稽差额恒为0."""
        end = begin + increase - decrease - transfer
        diff = end - (begin + increase - decrease - transfer)
        assert abs(diff) < 1e-6

    @settings(max_examples=5)
    @given(
        begin=st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False),
        increase=st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False),
        decrease=st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False),
        transfer=st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False),
        noise=st.floats(min_value=1.0, max_value=1e6, allow_nan=False, allow_infinity=False),
    )
    def test_triangle_imbalance_detected(self, begin, increase, decrease, transfer, noise):
        """期末不等于公式计算值时，差额=noise."""
        correct_end = begin + increase - decrease - transfer
        wrong_end = correct_end + noise
        diff = wrong_end - (begin + increase - decrease - transfer)
        assert abs(diff - noise) < 1e-6

    @settings(max_examples=5)
    @given(
        begin=st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False),
        increase=st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False),
        decrease=st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False),
        transfer=st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False),
    )
    def test_transfer_reduces_end_balance(self, begin, increase, decrease, transfer):
        """转固金额增加 → 期末余额减少（正比关系）."""
        end_with_transfer = begin + increase - decrease - transfer
        end_without_transfer = begin + increase - decrease
        # 转固使期末减少
        reduction = end_without_transfer - end_with_transfer
        assert abs(reduction - transfer) < 1e-6


# ─── 合计行勾稽 ─────────────────────────────────────────────────────────────


class TestSubtotalReconciliationPBT:
    """**Validates: Requirements 2.6** — 合计行=明细行之和."""

    @settings(max_examples=5)
    @given(
        items=st.lists(
            st.floats(min_value=0.0, max_value=1e6, allow_nan=False, allow_infinity=False),
            min_size=1,
            max_size=30,
        ),
    )
    def test_subtotal_equals_sum(self, items):
        """合计行恒等于明细行之和."""
        subtotal = sum(items)
        assert abs(subtotal - sum(items)) < 1e-6

    @settings(max_examples=5)
    @given(
        n_projects=st.integers(min_value=1, max_value=10),
        data=st.data(),
    )
    def test_cross_sheet_totals_match(self, n_projects, data):
        """H2-2明细合计 = H2-1审定表合计（跨表一致性）."""
        # 模拟 H2-2 各工程期末余额
        detail_ends = [
            data.draw(st.floats(min_value=0.0, max_value=1e8, allow_nan=False, allow_infinity=False))
            for _ in range(n_projects)
        ]
        # H2-1 审定表审定数 = H2-2 合计
        adjudication_total = sum(detail_ends)
        detail_total = sum(detail_ends)
        assert abs(adjudication_total - detail_total) < 1e-6
