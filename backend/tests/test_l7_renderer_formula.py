"""L7 其他非流动负债 — 渲染器负债类公式验证单元测试 (Task 5.1).

验证:
1. calc_liability_end_balance 负债类公式：期末=期初+贷方-借方
2. validate_liability_formula 行级校验逻辑
3. detect_negative_balances 负余额检测

Spec: .kiro/specs/l7-other-noncurrent-liabilities/
Task: 5.1

**Validates: Requirements 1.6**
"""

from __future__ import annotations

import json

from app.routers.wp_render_strategies._l7_other_noncurrent_liabilities import (
    calc_liability_end_balance,
    detect_negative_balances,
    validate_liability_formula,
)


# ─── calc_liability_end_balance ──────────────────────────────────────────


class TestCalcLiabilityEndBalance:
    def test_basic(self):
        """期末=100+50-30=120."""
        assert calc_liability_end_balance(100, 50, 30) == 120.0

    def test_zero_inputs(self):
        assert calc_liability_end_balance(0, 0, 0) == 0.0

    def test_credit_only(self):
        """仅增加（贷方），期末=期初+贷方."""
        assert calc_liability_end_balance(1000, 200, 0) == 1200.0

    def test_debit_only(self):
        """仅减少（借方），期末=期初-借方."""
        assert calc_liability_end_balance(1000, 0, 300) == 700.0

    def test_negative_result(self):
        """借方>期初+贷方，结果为负."""
        assert calc_liability_end_balance(100, 50, 200) == -50.0


# ─── validate_liability_formula ──────────────────────────────────────────


class TestValidateLiabilityFormula:
    def test_valid_row(self):
        """公式一致→无错误."""
        rows = [{"row_key": "r1", "begin": 100, "credit": 50, "debit": 30, "end": 120}]
        assert validate_liability_formula(rows) == []

    def test_invalid_row(self):
        """end=999 但 100+50-30=120 → 有偏差."""
        rows = [{"row_key": "r1", "begin": 100, "credit": 50, "debit": 30, "end": 999}]
        errors = validate_liability_formula(rows)
        assert len(errors) == 1
        assert errors[0]["row_key"] == "r1"
        assert errors[0]["field"] == "end_balance"
        assert "负债类公式不平衡" in errors[0]["message"]

    def test_all_zero_row_skipped(self):
        """全零行跳过."""
        rows = [{"row_key": "r0", "begin": 0, "credit": 0, "debit": 0, "end": 0}]
        assert validate_liability_formula(rows) == []

    def test_tolerance(self):
        """偏差<=0.01不报错."""
        rows = [{"row_key": "r1", "begin": 100, "credit": 50, "debit": 30, "end": 120.005}]
        assert validate_liability_formula(rows) == []

    def test_alternative_field_names(self):
        """支持 opening/closing 字段名."""
        rows = [{"item_id": "L7-1-row1", "opening": 200, "increase": 100, "decrease": 50, "closing": 250}]
        assert validate_liability_formula(rows) == []

    def test_multiple_rows_mixed(self):
        """多行混合：一对一错."""
        rows = [
            {"row_key": "ok", "begin": 500, "credit": 200, "debit": 100, "end": 600},
            {"row_key": "bad", "begin": 500, "credit": 200, "debit": 100, "end": 999},
        ]
        errors = validate_liability_formula(rows)
        assert len(errors) == 1
        assert errors[0]["row_key"] == "bad"


# ─── detect_negative_balances ────────────────────────────────────────────


class TestDetectNegativeBalances:
    def test_no_warnings_on_positive(self):
        """正常余额无警告."""
        snapshot = {
            "L7-1-item1": {"conclusion": json.dumps({"end_balance": 1000}), "remark": ""},
        }
        assert detect_negative_balances(snapshot) == []

    def test_detect_negative(self):
        """负余额触发警告."""
        snapshot = {
            "L7-1-item1": {"conclusion": json.dumps({"end_balance": -500}), "remark": ""},
        }
        warnings = detect_negative_balances(snapshot)
        assert len(warnings) == 1
        assert warnings[0]["item_id"] == "L7-1-item1"
        assert "-500" in warnings[0]["end_balance"]

    def test_ignores_non_l7_prefix(self):
        """非L7-前缀不检测."""
        snapshot = {
            "L5-item1": {"conclusion": json.dumps({"end_balance": -100}), "remark": ""},
        }
        assert detect_negative_balances(snapshot) == []

    def test_non_json_value_safe(self):
        """非JSON文本不崩溃."""
        snapshot = {
            "L7-2-row1": {"conclusion": "审计结论：无异常", "remark": ""},
        }
        assert detect_negative_balances(snapshot) == []

    def test_zero_balance_no_warning(self):
        """余额=0不警告."""
        snapshot = {
            "L7-1-item2": {"conclusion": json.dumps({"end_balance": 0}), "remark": ""},
        }
        assert detect_negative_balances(snapshot) == []
