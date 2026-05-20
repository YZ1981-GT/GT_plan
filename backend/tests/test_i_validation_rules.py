"""Tests for I 无形资产循环 3 条 VR (VR-I1-01 + VR-I3-01 + VR-I6-01)

Validates: Requirements I-F6
- VR-I1-01: 无形资产期末 = 期初 + 增加(I1-5) − 减少(I1-6) − 摊销(I1-10/I1-11) (blocking, tolerance=1.0)
- VR-I3-01: 商誉期末 = 期初 − 减值损失(I3-6) (blocking, tolerance=1.0)
- VR-I6-01: 研发费用总额 = 费用化(I6) + 资本化(I2) (blocking, tolerance=1.0)
  - 时机约束: I6 或 I2 任一未保存 → skip (passed=True, details="对方底稿未保存，跳过")

Spec: workpaper-i-intangible-assets-cycle / Sprint 2 / Task 2.14
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.services.consistency_gate import CheckItem, ConsistencyGate, ConsistencyResult


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
# Test JSON structure
# ---------------------------------------------------------------------------

class TestIValidationRulesJSON:
    """Test 3 条 VR JSON entries in i_cycle_validation_rules.json."""

    @pytest.fixture
    def rules_data(self):
        rules_path = (
            Path(__file__).parent.parent / "data" / "i_cycle_validation_rules.json"
        )
        with open(rules_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @pytest.fixture
    def i_rules(self, rules_data):
        return rules_data["rules"]

    def test_file_exists(self):
        rules_path = (
            Path(__file__).parent.parent / "data" / "i_cycle_validation_rules.json"
        )
        assert rules_path.exists(), "i_cycle_validation_rules.json missing"

    def test_three_i_rules_exist(self, i_rules):
        """3 条 VR-I1/I3/I6 规则存在"""
        ids = sorted(r["rule_id"] for r in i_rules)
        assert ids == ["VR-I1-01", "VR-I3-01", "VR-I6-01"]

    def test_vr_i1_01_blocking(self, i_rules):
        rule = next(r for r in i_rules if r["rule_id"] == "VR-I1-01")
        assert rule["severity"] == "blocking"
        assert rule["tolerance"] == 1.0
        assert rule["wp_code"] == "I1"

    def test_vr_i3_01_blocking(self, i_rules):
        rule = next(r for r in i_rules if r["rule_id"] == "VR-I3-01")
        assert rule["severity"] == "blocking"
        assert rule["tolerance"] == 1.0
        assert rule["wp_code"] == "I3"

    def test_vr_i6_01_blocking(self, i_rules):
        rule = next(r for r in i_rules if r["rule_id"] == "VR-I6-01")
        assert rule["severity"] == "blocking"
        assert rule["tolerance"] == 1.0
        assert rule["wp_code"] == "I6"

    def test_vr_i6_01_has_trigger_condition(self, i_rules):
        """VR-I6-01 含 trigger_condition 字段标记双底稿都保存才触发"""
        rule = next(r for r in i_rules if r["rule_id"] == "VR-I6-01")
        assert rule.get("trigger_condition") == "I6_and_I2_both_saved"

    def test_rules_have_required_fields(self, i_rules):
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
        for rule in i_rules:
            missing = required_fields - set(rule.keys())
            assert not missing, f"Rule {rule['rule_id']} missing fields: {missing}"

    def test_rule_type_is_cross_reconciliation(self, i_rules):
        for rule in i_rules:
            assert rule["rule_type"] == "cross_reconciliation"


# ---------------------------------------------------------------------------
# Test formula evaluation logic (mock data: pass/fail/skip scenarios)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestICycleTriangleLogic:
    """Test I 循环三角勾稽校验逻辑 — pass/fail/skip scenarios."""

    # --- VR-I1-01 ---

    async def test_vr_i1_01_pass(self, db_session, project_id):
        """VR-I1-01 通过: closing = opening + additions - disposals - amortization (差异 < 1.0)"""
        gate = ConsistencyGate(db_session)
        i1_data = {
            "intangible_asset_closing": "8000000.00",
            "intangible_asset_opening": "10000000.00",
            "intangible_asset_additions": "2000000.00",
            "intangible_asset_disposals": "1000000.00",
            "current_amortization": "3000000.00",  # 10M + 2M - 1M - 3M = 8M ✓
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "I1": i1_data, "I2": None, "I3": None, "I6": None
            }.get(code)
            checks = await gate.check_i_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "无形资产期末" in c.check_name)
        assert rule.passed is True
        assert rule.severity == "blocking"

    async def test_vr_i1_01_fail(self, db_session, project_id):
        """VR-I1-01 失败: 差异 > 1.0"""
        gate = ConsistencyGate(db_session)
        i1_data = {
            "intangible_asset_closing": "9000000.00",  # expected = 8M, diff = 1M
            "intangible_asset_opening": "10000000.00",
            "intangible_asset_additions": "2000000.00",
            "intangible_asset_disposals": "1000000.00",
            "current_amortization": "3000000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "I1": i1_data, "I2": None, "I3": None, "I6": None
            }.get(code)
            checks = await gate.check_i_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "无形资产期末" in c.check_name)
        assert rule.passed is False
        assert rule.severity == "blocking"

    async def test_vr_i1_01_skip(self, db_session, project_id):
        """VR-I1-01 数据缺失时跳过"""
        gate = ConsistencyGate(db_session)
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock, return_value=None
        ):
            checks = await gate.check_i_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "无形资产期末" in c.check_name)
        assert rule.passed is True
        assert "数据不完整" in rule.details

    async def test_vr_i1_01_boundary_within_tolerance(self, db_session, project_id):
        """VR-I1-01 边界: 差异 = 0.5 (< 1.0 通过)"""
        gate = ConsistencyGate(db_session)
        i1_data = {
            "intangible_asset_closing": "8000000.50",  # diff = 0.50
            "intangible_asset_opening": "10000000.00",
            "intangible_asset_additions": "2000000.00",
            "intangible_asset_disposals": "1000000.00",
            "current_amortization": "3000000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "I1": i1_data, "I2": None, "I3": None, "I6": None
            }.get(code)
            checks = await gate.check_i_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "无形资产期末" in c.check_name)
        assert rule.passed is True

    # --- VR-I3-01 ---

    async def test_vr_i3_01_pass(self, db_session, project_id):
        """VR-I3-01 通过: closing = opening - impairment_loss"""
        gate = ConsistencyGate(db_session)
        i3_data = {
            "goodwill_closing": "4500000.00",
            "goodwill_opening": "5000000.00",
            "goodwill_impairment_loss": "500000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "I1": None, "I2": None, "I3": i3_data, "I6": None
            }.get(code)
            checks = await gate.check_i_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "商誉期末" in c.check_name)
        assert rule.passed is True
        assert rule.severity == "blocking"

    async def test_vr_i3_01_pass_no_impairment(self, db_session, project_id):
        """VR-I3-01 通过: 无减值时 closing = opening"""
        gate = ConsistencyGate(db_session)
        i3_data = {
            "goodwill_closing": "5000000.00",
            "goodwill_opening": "5000000.00",
            "goodwill_impairment_loss": "0.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "I1": None, "I2": None, "I3": i3_data, "I6": None
            }.get(code)
            checks = await gate.check_i_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "商誉期末" in c.check_name)
        assert rule.passed is True

    async def test_vr_i3_01_fail(self, db_session, project_id):
        """VR-I3-01 失败: 差异 > 1.0"""
        gate = ConsistencyGate(db_session)
        i3_data = {
            "goodwill_closing": "4000000.00",  # expected = 5M - 0.5M = 4.5M, diff = 500K
            "goodwill_opening": "5000000.00",
            "goodwill_impairment_loss": "500000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "I1": None, "I2": None, "I3": i3_data, "I6": None
            }.get(code)
            checks = await gate.check_i_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "商誉期末" in c.check_name)
        assert rule.passed is False
        assert rule.severity == "blocking"

    async def test_vr_i3_01_skip(self, db_session, project_id):
        """VR-I3-01 数据缺失时跳过"""
        gate = ConsistencyGate(db_session)
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock, return_value=None
        ):
            checks = await gate.check_i_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "商誉期末" in c.check_name)
        assert rule.passed is True
        assert "数据不完整" in rule.details

    # --- VR-I6-01 (双底稿都保存才 blocking) ---

    async def test_vr_i6_01_pass_both_saved(self, db_session, project_id):
        """VR-I6-01 通过: I6 和 I2 都已保存, total = expensed + capitalized"""
        gate = ConsistencyGate(db_session)
        i6_data = {
            "rd_expense_total": "10000000.00",
            "rd_expensed": "7000000.00",
        }
        i2_data = {
            "rd_capitalized_amount": "3000000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "I1": None, "I2": i2_data, "I3": None, "I6": i6_data
            }.get(code)
            checks = await gate.check_i_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "研发费用" in c.check_name)
        assert rule.passed is True
        assert rule.severity == "blocking"

    async def test_vr_i6_01_fail_both_saved(self, db_session, project_id):
        """VR-I6-01 失败: 双底稿都保存但差异 > 1.0"""
        gate = ConsistencyGate(db_session)
        i6_data = {
            "rd_expense_total": "10000000.00",
            "rd_expensed": "5000000.00",  # 5M + 3M = 8M, diff = 2M
        }
        i2_data = {
            "rd_capitalized_amount": "3000000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "I1": None, "I2": i2_data, "I3": None, "I6": i6_data
            }.get(code)
            checks = await gate.check_i_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "研发费用" in c.check_name)
        assert rule.passed is False
        assert rule.severity == "blocking"

    async def test_vr_i6_01_skip_i2_not_saved(self, db_session, project_id):
        """VR-I6-01 跳过: I6 已保存但 I2 未保存 → skip 不阻断"""
        gate = ConsistencyGate(db_session)
        i6_data = {
            "rd_expense_total": "10000000.00",
            "rd_expensed": "7000000.00",
        }
        # I2 = None (未保存)
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "I1": None, "I2": None, "I3": None, "I6": i6_data
            }.get(code)
            checks = await gate.check_i_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "研发费用" in c.check_name)
        assert rule.passed is True
        assert "对方底稿未保存" in rule.details

    async def test_vr_i6_01_skip_i6_not_saved(self, db_session, project_id):
        """VR-I6-01 跳过: I2 已保存但 I6 未保存 → skip 不阻断"""
        gate = ConsistencyGate(db_session)
        i2_data = {
            "rd_capitalized_amount": "3000000.00",
        }
        # I6 = None (未保存)
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "I1": None, "I2": i2_data, "I3": None, "I6": None
            }.get(code)
            checks = await gate.check_i_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "研发费用" in c.check_name)
        assert rule.passed is True
        assert "对方底稿未保存" in rule.details

    async def test_vr_i6_01_skip_both_unsaved(self, db_session, project_id):
        """VR-I6-01 跳过: I6 和 I2 都未保存 → skip 不阻断"""
        gate = ConsistencyGate(db_session)
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock, return_value=None
        ):
            checks = await gate.check_i_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "研发费用" in c.check_name)
        assert rule.passed is True
        assert "对方底稿未保存" in rule.details

    async def test_vr_i6_01_skip_partial_field_missing(self, db_session, project_id):
        """VR-I6-01 跳过: I6 dict 存在但缺关键字段 → 视为未保存 skip"""
        gate = ConsistencyGate(db_session)
        i6_data = {
            "rd_expense_total": "10000000.00",
            # rd_expensed 缺失
        }
        i2_data = {
            "rd_capitalized_amount": "3000000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "I1": None, "I2": i2_data, "I3": None, "I6": i6_data
            }.get(code)
            checks = await gate.check_i_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "研发费用" in c.check_name)
        assert rule.passed is True
        assert "对方底稿未保存" in rule.details

    # --- Integration tests ---

    async def test_all_skip_when_no_data(self, db_session, project_id):
        """所有数据缺失时全部跳过 (passed=True), 长度=3"""
        gate = ConsistencyGate(db_session)
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock, return_value=None
        ):
            checks = await gate.check_i_cycle_triangle_reconciliation(project_id, 2025)

        assert len(checks) == 3
        for c in checks:
            assert c.passed is True

    async def test_blocking_rule_prevents_signoff(self, db_session, project_id):
        """VR-I1-01 blocking 失败时阻断签字"""
        gate = ConsistencyGate(db_session)
        i1_data = {
            "intangible_asset_closing": "9999999.00",  # diff > 1.0 from 8M
            "intangible_asset_opening": "10000000.00",
            "intangible_asset_additions": "2000000.00",
            "intangible_asset_disposals": "1000000.00",
            "current_amortization": "3000000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "I1": i1_data, "I2": None, "I3": None, "I6": None
            }.get(code)
            checks = await gate.check_i_cycle_triangle_reconciliation(project_id, 2025)

        result = ConsistencyResult(overall="fail", checks=checks)
        assert result.has_blocking_failures is True

    async def test_all_three_rules_returned(self, db_session, project_id):
        """check_i_cycle_triangle_reconciliation 始终返回 3 条规则结果"""
        gate = ConsistencyGate(db_session)
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock, return_value=None
        ):
            checks = await gate.check_i_cycle_triangle_reconciliation(project_id, 2025)

        assert len(checks) == 3
        check_names = " ".join(c.check_name for c in checks)
        assert "无形资产期末" in check_names
        assert "商誉期末" in check_names
        assert "研发费用" in check_names

    async def test_all_blocking_severity(self, db_session, project_id):
        """3 条 I 循环规则全部 severity=blocking"""
        gate = ConsistencyGate(db_session)
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock, return_value=None
        ):
            checks = await gate.check_i_cycle_triangle_reconciliation(project_id, 2025)

        for c in checks:
            assert c.severity == "blocking"


# ---------------------------------------------------------------------------
# Test integration with run_all_checks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestIIntegrationWithRunAllChecks:
    """Verify check_i_cycle_triangle_reconciliation is wired into run_all_checks."""

    async def test_i_cycle_checks_included(self, db_session, project_id):
        """run_all_checks 包含 3 条 I 循环三角勾稽规则"""
        gate = ConsistencyGate(db_session)
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock, return_value=None
        ):
            result = await gate.run_all_checks(project_id, 2025)

        i_check_names = [
            c.check_name for c in result.checks if c.check_name.startswith("I")
        ]
        assert len(i_check_names) >= 3
        joined = " ".join(i_check_names)
        assert "无形资产期末" in joined
        assert "商誉期末" in joined
        assert "研发费用" in joined

    async def test_i_blocking_failure_propagates_to_overall(self, db_session, project_id):
        """I 循环 blocking 失败时 overall=fail"""
        gate = ConsistencyGate(db_session)
        i1_data = {
            "intangible_asset_closing": "9999999.00",  # 差异远超 1.0
            "intangible_asset_opening": "10000000.00",
            "intangible_asset_additions": "2000000.00",
            "intangible_asset_disposals": "1000000.00",
            "current_amortization": "3000000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: (
                i1_data if code == "I1" else None
            )
            result = await gate.run_all_checks(project_id, 2025)

        assert result.overall == "fail"
        assert result.has_blocking_failures is True
