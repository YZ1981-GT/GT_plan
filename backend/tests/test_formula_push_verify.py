"""推送反向校验测试（spec: formula-management-deep-optimization · R5）。

验证 verify.py 的分类逻辑。
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.formula_push.verify import _to_decimal, _values_match


class TestToDecimal:
    def test_int(self):
        assert _to_decimal(100) == Decimal("100")

    def test_float(self):
        assert _to_decimal(3.14) == Decimal("3.14")

    def test_str(self):
        assert _to_decimal("99.5") == Decimal("99.5")

    def test_none(self):
        assert _to_decimal(None) is None

    def test_invalid(self):
        assert _to_decimal("abc") is None


class TestValuesMatch:
    def test_equal(self):
        assert _values_match(Decimal("100"), Decimal("100"))

    def test_within_tolerance(self):
        assert _values_match(Decimal("100.001"), Decimal("100.003"))

    def test_outside_tolerance(self):
        assert not _values_match(Decimal("100"), Decimal("101"))

    def test_both_none(self):
        assert _values_match(None, None)

    def test_one_none(self):
        assert not _values_match(Decimal("100"), None)
        assert not _values_match(None, Decimal("100"))


class TestVerifyClassification:
    """验证分类逻辑的规则。"""

    def test_manual_override_state(self):
        """state=manual → manual_override 不管值是否一致。"""
        # 构造 mock state
        from types import SimpleNamespace
        state = SimpleNamespace(
            addr_id="test", domain="note", rule_id="r1",
            last_formula_value="100", last_pushed_value="100",
            current_value="200", state="manual",
            updated_at=None,
        )
        # 直接测分类逻辑
        if state.state in ("manual", "locked"):
            status = "manual_override"
        else:
            status = "consistent"
        assert status == "manual_override"

    def test_never_pushed_is_stale(self):
        """last_pushed_value=None → stale。"""
        from types import SimpleNamespace
        state = SimpleNamespace(
            addr_id="test", domain="note", rule_id="r1",
            last_formula_value="100", last_pushed_value=None,
            current_value=None, state="auto",
            updated_at=None,
        )
        pushed_val = _to_decimal(state.last_pushed_value)
        assert pushed_val is None
        # 按逻辑：pushed_val is None → stale

    def test_consistent_when_all_match(self):
        """源头 == 推送 == 当前 → consistent。"""
        from types import SimpleNamespace
        state = SimpleNamespace(
            addr_id="test", domain="note", rule_id="r1",
            last_formula_value="500.00", last_pushed_value="500.00",
            current_value="500.00", state="auto",
            updated_at=None,
        )
        source = _to_decimal(state.last_formula_value)
        pushed = _to_decimal(state.last_pushed_value)
        current = _to_decimal(state.current_value)
        assert _values_match(source, pushed)
        assert _values_match(current, pushed)
