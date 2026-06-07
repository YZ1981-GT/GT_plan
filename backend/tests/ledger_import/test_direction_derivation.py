"""方向推导规则与符号异常检测测试。

覆盖 Task 4（方向推导）和 Task 5（异常检测）的核心逻辑。

Requirements: 1.1, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 4.1, 4.2, 4.3
"""

from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.ledger_import.direction_derivation import (
    CONTRA_ASSET_PATTERNS,
    CREDIT_KEYWORDS,
    DEBIT_KEYWORDS,
    NORMAL_DIRECTION_BY_CATEGORY,
    DerivationResult,
    derive_balance_direction,
)
from app.services.ledger_import.sign_anomaly_detector import (
    detect_sign_anomalies,
)


# ===========================================================================
# Task 4: 方向推导
# ===========================================================================


class TestExplicitDirection:
    """4.1 显式方向列：按借/贷/D/C/debit/credit 调符号。"""

    @pytest.mark.parametrize("direction_val", ["借", "借方", "D", "d", "debit", "Debit"])
    def test_debit_keywords(self, direction_val):
        row = {"direction": direction_val, "closing_balance": 1000}
        result = derive_balance_direction(row)
        assert result.direction == "debit"
        assert result.direction_source == "explicit_direction"

    @pytest.mark.parametrize("direction_val", ["贷", "贷方", "C", "c", "credit", "Credit"])
    def test_credit_keywords(self, direction_val):
        row = {"direction": direction_val, "closing_balance": 1000}
        result = derive_balance_direction(row)
        assert result.direction == "credit"
        assert result.direction_source == "explicit_direction"

    def test_explicit_priority_over_split_columns(self):
        """显式方向优先级高于借贷分列。"""
        row = {
            "direction": "贷",
            "closing_debit": 500,
            "closing_credit": 200,
        }
        result = derive_balance_direction(row)
        assert result.direction == "credit"
        assert result.direction_source == "explicit_direction"


class TestSplitColumns:
    """4.2 借贷分列：按借方列减贷方列计算净额并记录 split_columns。"""

    def test_only_debit_nonzero(self):
        row = {"closing_debit": 1000, "closing_credit": 0}
        result = derive_balance_direction(row)
        assert result.direction == "debit"
        assert result.direction_source == "split_columns"

    def test_only_credit_nonzero(self):
        row = {"closing_debit": 0, "closing_credit": 500}
        result = derive_balance_direction(row)
        assert result.direction == "credit"
        assert result.direction_source == "split_columns"

    def test_both_zero(self):
        row = {"closing_debit": 0, "closing_credit": 0}
        result = derive_balance_direction(row)
        assert result.direction == "unknown"
        assert result.direction_source == "split_columns"

    def test_opening_fallback(self):
        """期末分列无值时，回退到期初分列。"""
        row = {"opening_debit": 800, "opening_credit": 0}
        result = derive_balance_direction(row)
        assert result.direction == "debit"
        assert result.direction_source == "split_columns"


class TestBothDebitCreditNonzero:
    """4.3 借贷两方同时非零：按净额判定方向并记录 warning。"""

    def test_net_debit(self):
        row = {"closing_debit": 1000, "closing_credit": 300}
        result = derive_balance_direction(row)
        assert result.direction == "debit"
        assert result.direction_source == "split_columns"
        assert result.warning == "both_debit_credit_nonzero"

    def test_net_credit(self):
        row = {"closing_debit": 200, "closing_credit": 800}
        result = derive_balance_direction(row)
        assert result.direction == "credit"
        assert result.direction_source == "split_columns"
        assert result.warning == "both_debit_credit_nonzero"

    def test_net_zero(self):
        row = {"closing_debit": 500, "closing_credit": 500}
        result = derive_balance_direction(row)
        assert result.direction == "unknown"
        assert result.warning == "both_debit_credit_nonzero"


class TestCategoryInferred:
    """4.4 单一净额列：按 Account_Category / Contra_Asset 推断。"""

    def test_asset_debit(self):
        row = {"closing_balance": 1000, "account_code": "1001"}
        meta = {"account_category": "asset"}
        result = derive_balance_direction(row, meta)
        assert result.direction == "debit"
        assert result.direction_source == "account_category_inferred"

    def test_liability_credit(self):
        row = {"closing_balance": -500, "account_code": "2001"}
        meta = {"account_category": "liability"}
        result = derive_balance_direction(row, meta)
        assert result.direction == "credit"
        assert result.direction_source == "account_category_inferred"

    def test_contra_asset_credit(self):
        """资产备抵科目方向为贷方。"""
        row = {"closing_balance": -200, "account_name": "坏账准备"}
        meta = {"account_category": "asset", "is_contra_asset": True}
        result = derive_balance_direction(row, meta)
        assert result.direction == "credit"
        assert result.direction_source == "account_category_inferred"

    def test_contra_asset_by_name_pattern(self):
        """按名称识别资产备抵。"""
        row = {"closing_balance": -100, "account_name": "累计折旧"}
        meta = {"account_category": "asset"}
        result = derive_balance_direction(row, meta)
        assert result.direction == "credit"
        assert result.direction_source == "account_category_inferred"


class TestMetadataMissing:
    """4.5 metadata 缺失时标记 unknown，不强行猜测。"""

    def test_no_metadata_no_splits_no_direction(self):
        row = {"closing_balance": 1000, "account_code": "9999"}
        result = derive_balance_direction(row, None)
        # 9 开头不在前缀映射中
        assert result.direction == "unknown"
        assert result.direction_source == "unknown"

    def test_no_metadata_but_has_prefix(self):
        """有编码前缀时用低置信推断。"""
        row = {"closing_balance": 1000, "account_code": "1001"}
        result = derive_balance_direction(row, None)
        assert result.direction == "debit"
        assert result.direction_source == "account_category_inferred_low_confidence"


class TestLowConfidencePrefix:
    """4.8 科目编码前缀低置信推断只用于提示，不用于自动迁移改写。"""

    def test_prefix_1_is_asset(self):
        row = {"account_code": "1001"}
        result = derive_balance_direction(row, None)
        assert result.direction_source == "account_category_inferred_low_confidence"

    def test_prefix_2_is_liability(self):
        row = {"account_code": "2221"}
        result = derive_balance_direction(row, None)
        assert result.direction == "credit"
        assert result.direction_source == "account_category_inferred_low_confidence"


class TestSourceSplitAbsoluteValues:
    """4.7 源分列字段保持绝对值，仅净额字段带符号。

    derive_balance_direction 不改写行数据，只推导方向。
    验证它不 mutate 输入 row。
    """

    def test_row_not_mutated(self):
        row = {"closing_debit": 1000, "closing_credit": 300}
        original = dict(row)
        derive_balance_direction(row)
        assert row == original


class TestSignConventionStorage:
    """4.6 负债贷方余额存负、资产借方余额存正、资产备抵为贷方。

    验证推导方向与存储符号约定一致。
    """

    def test_liability_credit_balance_stored_negative(self):
        """负债科目贷方余额存负数 → direction=credit。"""
        row = {"closing_balance": -5000, "account_code": "2001"}
        meta = {"account_category": "liability"}
        result = derive_balance_direction(row, meta)
        assert result.direction == "credit"

    def test_asset_debit_balance_stored_positive(self):
        """资产科目借方余额存正数 → direction=debit。"""
        row = {"closing_balance": 10000, "account_code": "1001"}
        meta = {"account_category": "asset"}
        result = derive_balance_direction(row, meta)
        assert result.direction == "debit"

    def test_contra_asset_is_credit(self):
        """资产备抵为贷方。"""
        row = {"account_name": "累计摊销", "account_code": "1602"}
        meta = {"account_category": "asset", "is_contra_asset": True}
        result = derive_balance_direction(row, meta)
        assert result.direction == "credit"


# ===========================================================================
# Task 5: 符号异常检测
# ===========================================================================


class TestDetectSignAnomalies:
    """5.1 识别与 Account_Category 正常方向冲突的余额。"""

    def test_liability_debit_balance_flagged(self):
        """负债类借方净额被标记异常。"""
        rows = [
            {"account_code": "2221", "account_name": "应交税费",
             "closing_balance": 14203492},
        ]
        category_map = {
            "2221": {"account_category": "liability", "account_name": "应交税费"},
        }
        anomalies = detect_sign_anomalies(rows, category_map)
        assert len(anomalies) == 1
        assert anomalies[0].expected_direction == "credit"
        assert anomalies[0].actual_direction == "debit"
        assert anomalies[0].account_code == "2221"

    def test_asset_credit_balance_flagged(self):
        """资产类贷方净额被标记异常。"""
        rows = [
            {"account_code": "1001", "account_name": "库存现金",
             "closing_balance": -500},
        ]
        category_map = {
            "1001": {"account_category": "asset", "account_name": "库存现金"},
        }
        anomalies = detect_sign_anomalies(rows, category_map)
        assert len(anomalies) == 1
        assert anomalies[0].expected_direction == "debit"
        assert anomalies[0].actual_direction == "credit"

    def test_no_anomaly_when_direction_matches(self):
        """方向匹配时不产生异常。"""
        rows = [
            {"account_code": "1001", "closing_balance": 1000},
        ]
        category_map = {
            "1001": {"account_category": "asset"},
        }
        anomalies = detect_sign_anomalies(rows, category_map)
        assert len(anomalies) == 0


class TestDetectBothDebitCreditAndContra:
    """5.2 识别借贷并存、资产备抵反向、负债权益收入借方净额。"""

    def test_revenue_debit_flagged(self):
        """收入类借方净额异常。"""
        rows = [
            {"account_code": "6001", "account_name": "主营业务收入",
             "closing_balance": 1000},
        ]
        category_map = {
            "6001": {"account_category": "revenue", "account_name": "主营业务收入"},
        }
        anomalies = detect_sign_anomalies(rows, category_map)
        assert len(anomalies) == 1
        assert anomalies[0].reason == "revenue_debit_net_balance"

    def test_equity_debit_flagged(self):
        """权益类借方净额异常。"""
        rows = [
            {"account_code": "3001", "account_name": "实收资本",
             "closing_balance": 500},
        ]
        category_map = {
            "3001": {"account_category": "equity", "account_name": "实收资本"},
        }
        anomalies = detect_sign_anomalies(rows, category_map)
        assert len(anomalies) == 1
        assert anomalies[0].reason == "equity_debit_net_balance"

    def test_contra_asset_debit_flagged(self):
        """资产备抵借方余额异常。"""
        rows = [
            {"account_code": "1602", "account_name": "累计折旧",
             "closing_balance": 200},  # 正数=借方，备抵应为贷方
        ]
        category_map = {
            "1602": {
                "account_category": "asset",
                "is_contra_asset": True,
                "account_name": "累计折旧",
            },
        }
        anomalies = detect_sign_anomalies(rows, category_map)
        assert len(anomalies) == 1
        assert anomalies[0].reason == "contra_asset_debit_balance"

    def test_no_category_no_anomaly(self):
        """无类别映射时不产生异常。"""
        rows = [
            {"account_code": "9999", "closing_balance": 1000},
        ]
        anomalies = detect_sign_anomalies(rows, {})
        assert len(anomalies) == 0


# ===========================================================================
# Property-Based Tests
# ===========================================================================


class TestDirectionDerivationProperties:
    """PBT: 方向推导不变量。

    **Validates: Requirements 2.3, 2.4, 2.5**
    """

    @settings(max_examples=5)
    @given(
        debit=st.decimals(min_value=0, max_value=1_000_000, places=2),
        credit=st.decimals(min_value=0, max_value=1_000_000, places=2),
    )
    def test_split_columns_direction_matches_net_sign(self, debit, credit):
        """Property: 借贷分列推导方向与净额符号一致。"""
        row = {"closing_debit": float(debit), "closing_credit": float(credit)}
        result = derive_balance_direction(row)

        net = debit - credit
        if net > 0:
            assert result.direction == "debit"
        elif net < 0:
            assert result.direction == "credit"
        else:
            assert result.direction == "unknown"

    @settings(max_examples=5)
    @given(
        category=st.sampled_from(list(NORMAL_DIRECTION_BY_CATEGORY.keys())),
        code=st.text(
            alphabet="0123456789", min_size=4, max_size=4,
        ),
    )
    def test_category_inferred_returns_known_direction(self, category, code):
        """Property: 有 category metadata 时不返回 unknown。"""
        row = {"account_code": code}
        meta = {"account_category": category}
        result = derive_balance_direction(row, meta)
        assert result.direction in ("debit", "credit")
        assert result.direction_source == "account_category_inferred"
