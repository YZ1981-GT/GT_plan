"""历史数据 dry-run 脚本测试。

覆盖 Task 6 的核心逻辑：安全等级分类、冲突不改写、2221 等不能自动改写。

Requirements: 5.1, 5.2, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9
"""

import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# 确保 scripts/migrate 可被导入
_SCRIPTS_ROOT = Path(__file__).resolve().parents[2] / "scripts" / "migrate"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from sign_convention_dry_run import (
    DryRunItem,
    DryRunReport,
    classify_safety_level,
    run_dry_run,
)


# ===========================================================================
# classify_safety_level 单元测试
# ===========================================================================


class TestClassifySafetyLevel:
    """6.3 dry-run 输出三类安全等级。"""

    def test_no_conflict_returns_no_change(self):
        result = classify_safety_level(
            direction_source="split_columns",
            has_direction_conflict=False,
        )
        assert result == "no_change"

    def test_split_columns_conflict_returns_safe_auto_fix(self):
        result = classify_safety_level(
            direction_source="split_columns",
            has_direction_conflict=True,
            account_code="1001",
        )
        assert result == "safe_auto_fix"

    def test_explicit_direction_conflict_returns_safe_auto_fix(self):
        result = classify_safety_level(
            direction_source="explicit_direction",
            has_direction_conflict=True,
            account_code="1001",
        )
        assert result == "safe_auto_fix"

    def test_category_inferred_conflict_returns_manual_review(self):
        result = classify_safety_level(
            direction_source="account_category_inferred",
            has_direction_conflict=True,
            account_code="1001",
        )
        assert result == "manual_review_required"

    def test_low_confidence_returns_manual_review(self):
        result = classify_safety_level(
            direction_source="account_category_inferred_low_confidence",
            has_direction_conflict=True,
            account_code="5001",
        )
        assert result == "manual_review_required"


class TestSpecialAccountCodes:
    """6.8 2221 等可能真实反向余额不能仅凭科目类别自动改写。"""

    def test_2221_always_manual_review(self):
        """2221 应交税费即使有 split_columns 证据也不自动改写。"""
        result = classify_safety_level(
            direction_source="split_columns",
            has_direction_conflict=True,
            account_code="2221",
        )
        assert result == "manual_review_required"

    def test_2221_with_explicit_still_manual(self):
        """2221 即使有显式方向列证据也不自动改写。"""
        result = classify_safety_level(
            direction_source="explicit_direction",
            has_direction_conflict=True,
            account_code="2221",
        )
        assert result == "manual_review_required"

    def test_2241_always_manual(self):
        """2241 其他应付款也需人工复核。"""
        result = classify_safety_level(
            direction_source="split_columns",
            has_direction_conflict=True,
            account_code="2241",
        )
        assert result == "manual_review_required"


# ===========================================================================
# run_dry_run 集成测试
# ===========================================================================


class TestRunDryRun:
    """6.1~6.2 dry-run 报告输出。"""

    def test_no_conflict_items(self):
        """已符合约定的数据标记 no_change。"""
        rows = [
            {"account_code": "1001", "account_name": "库存现金",
             "closing_balance": 1000},
        ]
        category_map = {"1001": {"account_category": "asset"}}
        report = run_dry_run(rows, category_map, project_id="p1", dataset_id="d1")
        assert report.summary["no_change"] >= 1
        item = next(i for i in report.items if i.account_code == "1001")
        assert item.risk == "no_change"

    def test_conflict_detected(self):
        """方向冲突被检测到。"""
        rows = [
            {"account_code": "2001", "account_name": "短期借款",
             "closing_balance": 5000},  # 正数=借方，负债应为贷方
        ]
        category_map = {"2001": {"account_category": "liability"}}
        report = run_dry_run(rows, category_map)
        item = next(i for i in report.items if i.account_code == "2001")
        assert item.risk == "manual_review_required"

    def test_report_has_required_fields(self):
        """6.2 报告包含项目、dataset、科目、原金额、建议金额、原因、风险。"""
        rows = [
            {"account_code": "1001", "closing_balance": 1000},
        ]
        category_map = {"1001": {"account_category": "asset"}}
        report = run_dry_run(
            rows, category_map, project_id="proj-1", dataset_id="ds-1"
        )
        item = report.items[0]
        assert item.project_id == "proj-1"
        assert item.dataset_id == "ds-1"
        assert item.account_code == "1001"
        assert item.old_closing_balance
        assert item.suggested_closing_balance
        assert item.reason
        assert item.risk


class TestDryRunIdempotent:
    """6.4 重复执行不改变已符合约定的数据。"""

    def test_idempotent_no_change(self):
        """对同一数据两次 dry-run 结果一致。"""
        rows = [
            {"account_code": "1001", "closing_balance": 1000},
            {"account_code": "2001", "closing_balance": -500},
        ]
        category_map = {
            "1001": {"account_category": "asset"},
            "2001": {"account_category": "liability"},
        }
        r1 = run_dry_run(rows, category_map)
        r2 = run_dry_run(rows, category_map)
        assert r1.summary == r2.summary
        assert len(r1.items) == len(r2.items)


class TestConflictNoAutoWrite:
    """6.5 冲突项默认不改写。"""

    def test_default_no_allowlist_no_write(self):
        """无 allowlist 时，所有项为 dry-run（不改写建议金额=原金额 for manual_review）。"""
        rows = [
            {"account_code": "2221", "account_name": "应交税费",
             "closing_balance": 14203492},
        ]
        category_map = {"2221": {"account_category": "liability"}}
        report = run_dry_run(rows, category_map)
        item = next(i for i in report.items if i.account_code == "2221")
        # manual_review 不改金额
        assert item.suggested_closing_balance == item.old_closing_balance
        assert item.risk == "manual_review_required"


class TestAllowlistGuard:
    """6.6 执行脚本仅处理 allowlist。"""

    def test_run_dry_run_never_mutates_input(self):
        """dry-run 不修改输入行。"""
        rows = [
            {"account_code": "1001", "closing_balance": 1000},
        ]
        original = [dict(r) for r in rows]
        run_dry_run(rows, {"1001": {"account_category": "asset"}})
        assert rows == original


class TestDryRunReportJSON:
    """6.7 报告输出 JSON。"""

    def test_to_json_valid(self):
        rows = [
            {"account_code": "1001", "closing_balance": 1000},
        ]
        report = run_dry_run(rows, {"1001": {"account_category": "asset"}})
        json_str = report.to_json()
        parsed = json.loads(json_str)
        assert "items" in parsed
        assert "summary" in parsed


# ===========================================================================
# Property-Based Tests
# ===========================================================================


class TestDryRunProperties:
    """PBT: dry-run 不变量。

    **Validates: Requirements 5.4, 5.6, 5.8**
    """

    @settings(max_examples=5)
    @given(
        balance=st.decimals(
            min_value=-1_000_000, max_value=1_000_000, places=2,
            allow_nan=False, allow_infinity=False,
        ).filter(lambda x: x != 0),
    )
    def test_2221_never_safe_auto_fix(self, balance):
        """Property: 2221 应交税费永远不标记为 safe_auto_fix。"""
        rows = [
            {"account_code": "2221", "account_name": "应交税费",
             "closing_balance": str(balance)},
        ]
        category_map = {"2221": {"account_category": "liability"}}
        report = run_dry_run(rows, category_map)
        for item in report.items:
            if item.account_code == "2221":
                assert item.risk != "safe_auto_fix"

    @settings(max_examples=5)
    @given(
        balance=st.decimals(
            min_value=1, max_value=1_000_000, places=2,
            allow_nan=False, allow_infinity=False,
        ),
    )
    def test_asset_positive_balance_is_no_change(self, balance):
        """Property: 资产正余额（借方=正常）标记 no_change。"""
        rows = [
            {"account_code": "1001", "closing_balance": str(balance)},
        ]
        category_map = {"1001": {"account_category": "asset"}}
        report = run_dry_run(rows, category_map)
        item = next(i for i in report.items if i.account_code == "1001")
        assert item.risk == "no_change"
