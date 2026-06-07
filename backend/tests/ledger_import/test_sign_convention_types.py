"""符号约定类型一致性测试。

验证枚举值列表完备、SignAnomaly 可构造、常量与预期一致。
前端 fixture 对应 signConventionTypes.spec.ts。
"""

import pytest

from app.services.ledger_import.sign_convention_types import (
    CURRENT_SIGN_CONVENTION,
    DIRECTION_SOURCE_VALUES,
    MIGRATION_SAFETY_LEVEL_VALUES,
    SIGN_CONVENTION_VERSION_VALUES,
    SignAnomaly,
)

# ──────────────────────────────────────────────────────────────────────────────
# Golden fixtures — 前端 signConventionTypes.spec.ts 必须与此对齐
# ──────────────────────────────────────────────────────────────────────────────

GOLDEN_DIRECTION_SOURCE_VALUES = [
    "explicit_direction",
    "split_columns",
    "account_category_inferred",
    "account_category_inferred_low_confidence",
    "user_override",
    "legacy_inferred",
    "unknown",
]

GOLDEN_SIGN_CONVENTION_VERSION_VALUES = [
    "v1_net_debit_positive",
]

GOLDEN_MIGRATION_SAFETY_LEVEL_VALUES = [
    "safe_auto_fix",
    "manual_review_required",
    "no_change",
]


class TestDirectionSource:
    def test_values_match_golden(self):
        assert DIRECTION_SOURCE_VALUES == GOLDEN_DIRECTION_SOURCE_VALUES

    def test_no_duplicates(self):
        assert len(set(DIRECTION_SOURCE_VALUES)) == len(DIRECTION_SOURCE_VALUES)

    def test_count(self):
        assert len(DIRECTION_SOURCE_VALUES) == 7


class TestSignConventionVersion:
    def test_values_match_golden(self):
        assert SIGN_CONVENTION_VERSION_VALUES == GOLDEN_SIGN_CONVENTION_VERSION_VALUES

    def test_current_convention_in_values(self):
        assert CURRENT_SIGN_CONVENTION in SIGN_CONVENTION_VERSION_VALUES

    def test_current_is_v1(self):
        assert CURRENT_SIGN_CONVENTION == "v1_net_debit_positive"


class TestMigrationSafetyLevel:
    def test_values_match_golden(self):
        assert MIGRATION_SAFETY_LEVEL_VALUES == GOLDEN_MIGRATION_SAFETY_LEVEL_VALUES

    def test_no_duplicates(self):
        assert len(set(MIGRATION_SAFETY_LEVEL_VALUES)) == len(MIGRATION_SAFETY_LEVEL_VALUES)

    def test_count(self):
        assert len(MIGRATION_SAFETY_LEVEL_VALUES) == 3


class TestSignAnomaly:
    def test_construction(self):
        anomaly = SignAnomaly(
            account_code="2221",
            account_name="应交税费",
            expected_direction="credit",
            actual_direction="debit",
            balance_amount=14203492.00,
            category="liability",
            reason="liability_normal_credit",
        )
        assert anomaly.account_code == "2221"
        assert anomaly.expected_direction == "credit"
        assert anomaly.actual_direction == "debit"
        assert anomaly.balance_amount == 14203492.00

    def test_optional_account_name(self):
        anomaly = SignAnomaly(
            account_code="1001",
            account_name=None,
            expected_direction="debit",
            actual_direction="credit",
            balance_amount=-500.0,
            category="asset",
            reason="asset_credit_balance",
        )
        assert anomaly.account_name is None

    def test_serialization(self):
        anomaly = SignAnomaly(
            account_code="6001",
            account_name="主营业务收入",
            expected_direction="credit",
            actual_direction="debit",
            balance_amount=1000.0,
            category="revenue",
            reason="revenue_debit_balance",
        )
        data = anomaly.model_dump()
        assert data["account_code"] == "6001"
        assert data["reason"] == "revenue_debit_balance"
