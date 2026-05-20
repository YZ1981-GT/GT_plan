"""Tests for N 税金循环 2 条 VR (VR-N2-01 + VR-N5-01)

Validates: Requirements N-F3
- VR-N2-01: N2 应交税费期末 = 期初 + 计提 − 缴纳 (blocking, tolerance=1.0)
  - 时机约束: N2-1 saved；N2-1 未保存 → skip
- VR-N5-01: N5 所得税费用 ≈ 利润总额 × 税率 + 递延调整 (warning, tolerance=1.0)
  - 汇总类规则时机铁律: N5 + PL saved → 触发；利润总额未保存 → skip

Spec: workpaper-n-tax-cycle / Sprint 1 / Task 1.2
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.services.consistency_gate import CheckItem, ConsistencyGate


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def project_id():
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# Test JSON structure (VR-N2-01 + VR-N5-01 entries exist)
# ---------------------------------------------------------------------------

class TestNValidationRulesJSON:
    """Test 2 条 VR JSON entries in n_cycle_validation_rules.json."""

    @pytest.fixture
    def rules_data(self):
        rules_path = (
            Path(__file__).parent.parent / "data" / "n_cycle_validation_rules.json"
        )
        with open(rules_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @pytest.fixture
    def n_rules(self, rules_data):
        return rules_data["rules"]

    def test_file_exists(self):
        rules_path = (
            Path(__file__).parent.parent / "data" / "n_cycle_validation_rules.json"
        )
        assert rules_path.exists(), "n_cycle_validation_rules.json missing"

    def test_two_n_rules_exist(self, n_rules):
        """2 条 VR-N2-01/N5-01 规则存在"""
        ids = sorted(r["rule_id"] for r in n_rules)
        assert ids == ["VR-N2-01", "VR-N5-01"]

    def test_vr_n2_01_blocking(self, n_rules):
        rule = next(r for r in n_rules if r["rule_id"] == "VR-N2-01")
        assert rule["severity"] == "blocking"
        assert rule["tolerance"] == 1.0
        assert rule["wp_code"] == "N2"

    def test_vr_n5_01_warning(self, n_rules):
        rule = next(r for r in n_rules if r["rule_id"] == "VR-N5-01")
        assert rule["severity"] == "warning"
        assert rule["tolerance"] == 1.0
        assert rule["wp_code"] == "N5"

    def test_vr_n5_01_has_summary_rule_timing(self, n_rules):
        """VR-N5-01 遵循汇总类规则时机铁律：required_any_of_subs 配置 PL"""
        rule = next(r for r in n_rules if r["rule_id"] == "VR-N5-01")
        assert "applies_when" in rule
        applies = rule["applies_when"]
        assert applies.get("required_main_wp") == "N5"
        any_subs = applies.get("required_any_of_subs", [])
        assert "PL" in any_subs

    def test_vr_n2_01_no_sub_dependencies(self, n_rules):
        """VR-N2-01 无外部来源依赖（仅 N2-1 自身）"""
        rule = next(r for r in n_rules if r["rule_id"] == "VR-N2-01")
        assert "applies_when" in rule
        applies = rule["applies_when"]
        assert applies.get("required_main_wp") == "N2"
        assert applies.get("required_any_of_subs") == []

    def test_rules_have_required_fields(self, n_rules):
        required_fields = {
            "rule_id",
            "rule_type",
            "wp_code",
            "description",
            "formula",
            "tolerance",
            "severity",
            "sources",
            "message_template",
        }
        for rule in n_rules:
            missing = required_fields - set(rule.keys())
            assert not missing, f"Rule {rule['rule_id']} missing fields: {missing}"

    def test_rule_type_is_cross_reconciliation(self, n_rules):
        for rule in n_rules:
            assert rule["rule_type"] == "cross_reconciliation"


# ---------------------------------------------------------------------------
# Test formula evaluation logic — pass/fail/skip scenarios
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestNCycleTriangleLogic:
    """Test N 循环三角勾稽校验逻辑 — pass/fail/skip scenarios."""

    # --- VR-N2-01: N2 应交税费期末 = 期初 + 计提 − 缴纳 ---

    async def test_vr_n2_01_pass(self, db_session, project_id):
        """VR-N2-01 通过: N2 期末 = 期初 + 计提 − 缴纳 (差异 = 0)"""
        gate = ConsistencyGate(db_session)
        # 期末 = 100万 + 80万 − 70万 = 110万
        n2_data = {
            "n2_closing": "1100000.00",
            "n2_opening": "1000000.00",
            "n2_accrued": "800000.00",
            "n2_paid": "700000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "N2": n2_data, "N5": None, "PL": None,
            }.get(code)
            checks = await gate.check_n_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "N2勾稽" in c.check_name)
        assert rule.passed is True
        assert rule.severity == "blocking"

    async def test_vr_n2_01_pass_within_tolerance(self, db_session, project_id):
        """VR-N2-01 通过: 差异 < 1.0 (tolerance boundary, drift=0.99)"""
        gate = ConsistencyGate(db_session)
        # expected = 100万 + 80万 − 70万 = 110万；actual = 110万 + 0.99
        n2_data = {
            "n2_closing": "1100000.99",
            "n2_opening": "1000000.00",
            "n2_accrued": "800000.00",
            "n2_paid": "700000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "N2": n2_data, "N5": None, "PL": None,
            }.get(code)
            checks = await gate.check_n_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "N2勾稽" in c.check_name)
        assert rule.passed is True

    async def test_vr_n2_01_fail_blocking(self, db_session, project_id):
        """VR-N2-01 失败 (blocking): 差异 >= 1.0 (drift=1.5)"""
        gate = ConsistencyGate(db_session)
        # expected = 100万 + 80万 − 70万 = 110万；actual = 110万 + 1.5
        n2_data = {
            "n2_closing": "1100001.50",
            "n2_opening": "1000000.00",
            "n2_accrued": "800000.00",
            "n2_paid": "700000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "N2": n2_data, "N5": None, "PL": None,
            }.get(code)
            checks = await gate.check_n_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "N2勾稽" in c.check_name)
        assert rule.passed is False
        assert rule.severity == "blocking"

    async def test_vr_n2_01_fail_at_boundary(self, db_session, project_id):
        """VR-N2-01 失败: 差异恰好 = 1.0 (边界 — 不通过，因为 < 1.0 才通过)"""
        gate = ConsistencyGate(db_session)
        # expected = 100万 + 80万 − 70万 = 110万；actual = 110万 + 1.0
        n2_data = {
            "n2_closing": "1100001.00",
            "n2_opening": "1000000.00",
            "n2_accrued": "800000.00",
            "n2_paid": "700000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "N2": n2_data, "N5": None, "PL": None,
            }.get(code)
            checks = await gate.check_n_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "N2勾稽" in c.check_name)
        assert rule.passed is False

    async def test_vr_n2_01_pass_drift_zero(self, db_session, project_id):
        """VR-N2-01 通过: drift = 0 (完全匹配)"""
        gate = ConsistencyGate(db_session)
        n2_data = {
            "n2_closing": "500000.00",
            "n2_opening": "300000.00",
            "n2_accrued": "400000.00",
            "n2_paid": "200000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "N2": n2_data, "N5": None, "PL": None,
            }.get(code)
            checks = await gate.check_n_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "N2勾稽" in c.check_name)
        assert rule.passed is True

    async def test_vr_n2_01_pass_negative_drift(self, db_session, project_id):
        """VR-N2-01 通过: drift = -0.99 (负方向容差内)"""
        gate = ConsistencyGate(db_session)
        # expected = 300000 + 400000 - 200000 = 500000; actual = 500000 - 0.99
        n2_data = {
            "n2_closing": "499999.01",
            "n2_opening": "300000.00",
            "n2_accrued": "400000.00",
            "n2_paid": "200000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "N2": n2_data, "N5": None, "PL": None,
            }.get(code)
            checks = await gate.check_n_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "N2勾稽" in c.check_name)
        assert rule.passed is True

    async def test_vr_n2_01_skip_not_saved(self, db_session, project_id):
        """VR-N2-01 跳过: N2-1 审定表未保存"""
        gate = ConsistencyGate(db_session)
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "N2": None, "N5": None, "PL": None,
            }.get(code)
            checks = await gate.check_n_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "N2勾稽" in c.check_name)
        assert rule.passed is True
        assert "跳过" in rule.details

    async def test_vr_n2_01_skip_partial_data(self, db_session, project_id):
        """VR-N2-01 跳过: N2 仅有期末无期初"""
        gate = ConsistencyGate(db_session)
        n2_data = {"n2_closing": "1100000.00"}  # 无 n2_opening
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "N2": n2_data, "N5": None, "PL": None,
            }.get(code)
            checks = await gate.check_n_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "N2勾稽" in c.check_name)
        assert rule.passed is True
        assert "跳过" in rule.details

    # --- VR-N5-01: N5 所得税费用 ≈ 利润总额 × 税率 + 递延调整 ---

    async def test_vr_n5_01_pass(self, db_session, project_id):
        """VR-N5-01 通过: N5 = 利润总额 × 税率 + 递延调整 (差异 = 0)"""
        gate = ConsistencyGate(db_session)
        # 所得税 = 1000万 × 0.25 + (-50万) = 200万
        n5_data = {
            "n5_total": "2000000.00",
            "statutory_rate": "0.25",
            "deferred_adjustment": "-500000.00",
        }
        pl_data = {"profit_before_tax": "10000000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "N2": None, "N5": n5_data, "PL": pl_data,
            }.get(code)
            checks = await gate.check_n_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "N5勾稽" in c.check_name)
        assert rule.passed is True
        assert rule.severity == "warning"

    async def test_vr_n5_01_pass_within_tolerance(self, db_session, project_id):
        """VR-N5-01 通过: 差异 < 1.0 (drift=0.99)"""
        gate = ConsistencyGate(db_session)
        # expected = 1000万 × 0.25 + 0 = 250万；actual = 250万 + 0.99
        n5_data = {
            "n5_total": "2500000.99",
            "statutory_rate": "0.25",
            "deferred_adjustment": "0",
        }
        pl_data = {"profit_before_tax": "10000000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "N2": None, "N5": n5_data, "PL": pl_data,
            }.get(code)
            checks = await gate.check_n_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "N5勾稽" in c.check_name)
        assert rule.passed is True

    async def test_vr_n5_01_warn_when_drift_exceeds_tolerance(self, db_session, project_id):
        """VR-N5-01 警告 (warning): 差异 >= 1.0 (drift=1.5)"""
        gate = ConsistencyGate(db_session)
        # expected = 1000万 × 0.25 + 0 = 250万；actual = 260万；diff = 10万
        n5_data = {
            "n5_total": "2600000.00",
            "statutory_rate": "0.25",
            "deferred_adjustment": "0",
        }
        pl_data = {"profit_before_tax": "10000000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "N2": None, "N5": n5_data, "PL": pl_data,
            }.get(code)
            checks = await gate.check_n_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "N5勾稽" in c.check_name)
        assert rule.passed is False
        assert rule.severity == "warning"

    async def test_vr_n5_01_fail_at_boundary(self, db_session, project_id):
        """VR-N5-01 失败: 差异恰好 = 1.0 (边界 — 不通过)"""
        gate = ConsistencyGate(db_session)
        # expected = 1000万 × 0.25 + 0 = 250万；actual = 250万 + 1.0
        n5_data = {
            "n5_total": "2500001.00",
            "statutory_rate": "0.25",
            "deferred_adjustment": "0",
        }
        pl_data = {"profit_before_tax": "10000000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "N2": None, "N5": n5_data, "PL": pl_data,
            }.get(code)
            checks = await gate.check_n_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "N5勾稽" in c.check_name)
        assert rule.passed is False

    async def test_vr_n5_01_skip_profit_not_saved(self, db_session, project_id):
        """VR-N5-01 跳过: 利润总额（PL）未保存（汇总类规则时机铁律）"""
        gate = ConsistencyGate(db_session)
        n5_data = {
            "n5_total": "2500000.00",
            "statutory_rate": "0.25",
            "deferred_adjustment": "0",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "N2": None, "N5": n5_data, "PL": None,
            }.get(code)
            checks = await gate.check_n_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "N5勾稽" in c.check_name)
        assert rule.passed is True
        assert "跳过" in rule.details

    async def test_vr_n5_01_skip_n5_not_saved(self, db_session, project_id):
        """VR-N5-01 跳过: N5 审定表未保存"""
        gate = ConsistencyGate(db_session)
        pl_data = {"profit_before_tax": "10000000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "N2": None, "N5": None, "PL": pl_data,
            }.get(code)
            checks = await gate.check_n_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "N5勾稽" in c.check_name)
        assert rule.passed is True
        assert "跳过" in rule.details

    async def test_vr_n5_01_default_rate(self, db_session, project_id):
        """VR-N5-01 使用默认税率 0.25 当 statutory_rate 未提供"""
        gate = ConsistencyGate(db_session)
        # expected = 1000万 × 0.25 + 0 = 250万
        n5_data = {
            "n5_total": "2500000.00",
            "deferred_adjustment": "0",
        }  # 无 statutory_rate
        pl_data = {"profit_before_tax": "10000000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "N2": None, "N5": n5_data, "PL": pl_data,
            }.get(code)
            checks = await gate.check_n_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "N5勾稽" in c.check_name)
        assert rule.passed is True

    # --- Combined: all data None → all skip ---

    async def test_all_none_returns_two_skip_checks(self, db_session, project_id):
        """全部底稿未保存 → 2 条规则全部 skip 但 passed=True"""
        gate = ConsistencyGate(db_session)
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock, return_value=None
        ):
            checks = await gate.check_n_cycle_triangle_reconciliation(project_id, 2025)

        # 2 条规则全部 skip 但 passed=True
        assert len(checks) == 2
        assert all(c.passed is True for c in checks)
        assert all("跳过" in c.details for c in checks)

    # --- Integration: check_n_cycle_triangle_reconciliation integrates with consistency_gate ---

    async def test_integration_with_consistency_gate(self, db_session, project_id):
        """check_n_cycle_triangle_reconciliation 集成到 ConsistencyGate.run_all_checks"""
        gate = ConsistencyGate(db_session)
        # Verify the method exists and is callable
        assert hasattr(gate, "check_n_cycle_triangle_reconciliation")
        assert callable(gate.check_n_cycle_triangle_reconciliation)

        # Verify it returns list[CheckItem]
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock, return_value=None
        ):
            checks = await gate.check_n_cycle_triangle_reconciliation(project_id, 2025)

        assert isinstance(checks, list)
        assert all(isinstance(c, CheckItem) for c in checks)
        assert len(checks) == 2

    # --- Boundary cases: drift = 0, ±0.99, ±1.0, ±1.5 ---

    @pytest.mark.parametrize("drift,expected_pass", [
        ("0", True),
        ("0.99", True),
        ("-0.99", True),
        ("1.0", False),
        ("-1.0", False),
        ("1.5", False),
        ("-1.5", False),
    ])
    async def test_vr_n2_01_boundary_cases(self, db_session, project_id, drift, expected_pass):
        """VR-N2-01 边界测试: drift = {drift} → passed = {expected_pass}"""
        gate = ConsistencyGate(db_session)
        base_expected = Decimal("1000000.00")  # opening + accrued - paid
        actual = base_expected + Decimal(drift)
        n2_data = {
            "n2_closing": str(actual),
            "n2_opening": "500000.00",
            "n2_accrued": "800000.00",
            "n2_paid": "300000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "N2": n2_data, "N5": None, "PL": None,
            }.get(code)
            checks = await gate.check_n_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "N2勾稽" in c.check_name)
        assert rule.passed is expected_pass, (
            f"drift={drift}: expected passed={expected_pass}, got {rule.passed}"
        )

    @pytest.mark.parametrize("drift,expected_pass", [
        ("0", True),
        ("0.99", True),
        ("-0.99", True),
        ("1.0", False),
        ("-1.0", False),
        ("1.5", False),
        ("-1.5", False),
    ])
    async def test_vr_n5_01_boundary_cases(self, db_session, project_id, drift, expected_pass):
        """VR-N5-01 边界测试: drift = {drift} → passed = {expected_pass}"""
        gate = ConsistencyGate(db_session)
        # expected = 10000000 × 0.25 + 0 = 2500000
        base_expected = Decimal("2500000.00")
        actual = base_expected + Decimal(drift)
        n5_data = {
            "n5_total": str(actual),
            "statutory_rate": "0.25",
            "deferred_adjustment": "0",
        }
        pl_data = {"profit_before_tax": "10000000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "N2": None, "N5": n5_data, "PL": pl_data,
            }.get(code)
            checks = await gate.check_n_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "N5勾稽" in c.check_name)
        assert rule.passed is expected_pass, (
            f"drift={drift}: expected passed={expected_pass}, got {rule.passed}"
        )
