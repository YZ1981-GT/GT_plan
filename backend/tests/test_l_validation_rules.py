"""Tests for L 筹资循环 3 条 VR (VR-L8-01 + VR-L1-01 + VR-L3-01)

Validates: Requirements L-F3
- VR-L8-01: L8 利息支出 = L1利息 + L3利息 + H9租赁利息 + L5债券利息 (blocking, tolerance=1.0)
  - 汇总类规则时机铁律: L8 + 至少 1 个来源 saved → 触发；全部来源未保存 → skip
- VR-L1-01: L1 期末 = 期初 + 新增借款 − 偿还 (blocking, tolerance=1.0)
  - 时机约束: L1-1 saved；L1-1 未保存 → skip
- VR-L3-01: L3 期末 + 重分类 = 期初 + 新增 − 偿还 (warning, tolerance=1.0)
  - 时机约束: L3-1 saved；L3-1 未保存 → skip

Spec: workpaper-l-debt-cycle / Sprint 1 / Task 1.4
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
# Test JSON structure (VR-L8-01 + VR-L1-01 + VR-L3-01 entries exist)
# ---------------------------------------------------------------------------

class TestLValidationRulesJSON:
    """Test 3 条 VR JSON entries in l_cycle_validation_rules.json."""

    @pytest.fixture
    def rules_data(self):
        rules_path = (
            Path(__file__).parent.parent / "data" / "l_cycle_validation_rules.json"
        )
        with open(rules_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @pytest.fixture
    def l_rules(self, rules_data):
        return rules_data["rules"]

    def test_file_exists(self):
        rules_path = (
            Path(__file__).parent.parent / "data" / "l_cycle_validation_rules.json"
        )
        assert rules_path.exists(), "l_cycle_validation_rules.json missing"

    def test_three_l_rules_exist(self, l_rules):
        """3 条 VR-L8-01/L1-01/L3-01 规则存在"""
        ids = sorted(r["rule_id"] for r in l_rules)
        assert ids == ["VR-L1-01", "VR-L3-01", "VR-L8-01"]

    def test_vr_l8_01_blocking(self, l_rules):
        rule = next(r for r in l_rules if r["rule_id"] == "VR-L8-01")
        assert rule["severity"] == "blocking"
        assert rule["tolerance"] == 1.0
        assert rule["wp_code"] == "L8"

    def test_vr_l1_01_blocking(self, l_rules):
        rule = next(r for r in l_rules if r["rule_id"] == "VR-L1-01")
        assert rule["severity"] == "blocking"
        assert rule["tolerance"] == 1.0
        assert rule["wp_code"] == "L1"

    def test_vr_l3_01_warning(self, l_rules):
        rule = next(r for r in l_rules if r["rule_id"] == "VR-L3-01")
        assert rule["severity"] == "warning"
        assert rule["tolerance"] == 1.0
        assert rule["wp_code"] == "L3"

    def test_vr_l8_01_has_summary_rule_timing(self, l_rules):
        """VR-L8-01 遵循汇总类规则时机铁律：required_any_of_subs 配置 L1/L3/H9/L5"""
        rule = next(r for r in l_rules if r["rule_id"] == "VR-L8-01")
        assert "applies_when" in rule
        applies = rule["applies_when"]
        assert applies.get("required_main_wp") == "L8"
        any_subs = applies.get("required_any_of_subs", [])
        assert set(any_subs) >= {"L1", "L3", "H9", "L5"}

    def test_rules_have_required_fields(self, l_rules):
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
        for rule in l_rules:
            missing = required_fields - set(rule.keys())
            assert not missing, f"Rule {rule['rule_id']} missing fields: {missing}"

    def test_rule_type_is_cross_reconciliation(self, l_rules):
        for rule in l_rules:
            assert rule["rule_type"] == "cross_reconciliation"


# ---------------------------------------------------------------------------
# Test formula evaluation logic — pass/fail/skip scenarios
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestLCycleTriangleLogic:
    """Test L 循环三角勾稽校验逻辑 — pass/fail/skip scenarios."""

    # --- VR-L8-01: L8 利息支出 = L1 + L3 + H9 + L5 利息 ---

    async def test_vr_l8_01_pass(self, db_session, project_id):
        """VR-L8-01 通过: L8 = L1利息 + L3利息 + H9租赁利息 + L5债券利息 (差异 = 0)"""
        gate = ConsistencyGate(db_session)
        # L8 = 50万 + 80万 + 20万 + 30万 = 180万
        l8_data = {"l8_interest": "1800000.00"}
        l1_data = {"l1_interest": "500000.00"}
        l3_data = {"l3_interest": "800000.00"}
        h9_data = {"h9_lease_interest": "200000.00"}
        l5_data = {"l5_bond_interest": "300000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "L8": l8_data, "L1": l1_data, "L3": l3_data,
                "H9": h9_data, "L5": l5_data,
            }.get(code)
            checks = await gate.check_l_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "L8勾稽" in c.check_name)
        assert rule.passed is True
        assert rule.severity == "blocking"

    async def test_vr_l8_01_fail(self, db_session, project_id):
        """VR-L8-01 失败: 差异 > 1.0"""
        gate = ConsistencyGate(db_session)
        # expected = 50万 + 80万 + 20万 + 30万 = 180万；actual = 200万；diff = 20万
        l8_data = {"l8_interest": "2000000.00"}
        l1_data = {"l1_interest": "500000.00"}
        l3_data = {"l3_interest": "800000.00"}
        h9_data = {"h9_lease_interest": "200000.00"}
        l5_data = {"l5_bond_interest": "300000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "L8": l8_data, "L1": l1_data, "L3": l3_data,
                "H9": h9_data, "L5": l5_data,
            }.get(code)
            checks = await gate.check_l_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "L8勾稽" in c.check_name)
        assert rule.passed is False
        assert rule.severity == "blocking"

    async def test_vr_l8_01_skip_all_sources_unsaved(self, db_session, project_id):
        """VR-L8-01 跳过: L1/L3/H9/L5 全部未保存（汇总类规则时机铁律）"""
        gate = ConsistencyGate(db_session)
        l8_data = {"l8_interest": "1800000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "L8": l8_data, "L1": None, "L3": None,
                "H9": None, "L5": None,
            }.get(code)
            checks = await gate.check_l_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "L8勾稽" in c.check_name)
        assert rule.passed is True
        assert "跳过" in rule.details

    async def test_vr_l8_01_skip_l8_not_saved(self, db_session, project_id):
        """VR-L8-01 跳过: L8 审定数缺失"""
        gate = ConsistencyGate(db_session)
        l1_data = {"l1_interest": "500000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "L8": None, "L1": l1_data, "L3": None,
                "H9": None, "L5": None,
            }.get(code)
            checks = await gate.check_l_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "L8勾稽" in c.check_name)
        assert rule.passed is True
        assert "跳过" in rule.details

    async def test_vr_l8_01_partial_sources_triggers_check(self, db_session, project_id):
        """VR-L8-01 部分来源已保存: 仅 L1 已保存 → 仍触发校验"""
        gate = ConsistencyGate(db_session)
        # L8 = 180万；仅 L1 = 50万；expected = 50万；diff = 130万 → fail
        l8_data = {"l8_interest": "1800000.00"}
        l1_data = {"l1_interest": "500000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "L8": l8_data, "L1": l1_data, "L3": None,
                "H9": None, "L5": None,
            }.get(code)
            checks = await gate.check_l_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "L8勾稽" in c.check_name)
        # 部分来源已保存 → 触发校验（不 skip）
        assert rule.severity == "blocking"
        # 差异 = |180万 - 50万| = 130万 > 1.0 → fail
        assert rule.passed is False


    # --- VR-L1-01: L1 期末 = 期初 + 新增 − 偿还 ---

    async def test_vr_l1_01_pass(self, db_session, project_id):
        """VR-L1-01 通过: L1 期末 = 期初 + 新增 − 偿还 (差异 = 0)"""
        gate = ConsistencyGate(db_session)
        # 期末 = 1000万 + 500万 − 300万 = 1200万
        l1_data = {
            "l1_closing": "12000000.00",
            "l1_opening": "10000000.00",
            "l1_new_borrowings": "5000000.00",
            "l1_repayments": "3000000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "L8": None, "L1": l1_data, "L3": None,
                "H9": None, "L5": None,
            }.get(code)
            checks = await gate.check_l_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "L1勾稽" in c.check_name)
        assert rule.passed is True
        assert rule.severity == "blocking"

    async def test_vr_l1_01_fail(self, db_session, project_id):
        """VR-L1-01 失败: 差异 > 1.0"""
        gate = ConsistencyGate(db_session)
        # expected = 1000万 + 500万 − 300万 = 1200万；actual = 1500万；diff = 300万
        l1_data = {
            "l1_closing": "15000000.00",
            "l1_opening": "10000000.00",
            "l1_new_borrowings": "5000000.00",
            "l1_repayments": "3000000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "L8": None, "L1": l1_data, "L3": None,
                "H9": None, "L5": None,
            }.get(code)
            checks = await gate.check_l_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "L1勾稽" in c.check_name)
        assert rule.passed is False
        assert rule.severity == "blocking"

    async def test_vr_l1_01_skip_l1_not_saved(self, db_session, project_id):
        """VR-L1-01 跳过: L1-1 审定表未保存（期末缺失）"""
        gate = ConsistencyGate(db_session)
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "L8": None, "L1": None, "L3": None,
                "H9": None, "L5": None,
            }.get(code)
            checks = await gate.check_l_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "L1勾稽" in c.check_name)
        assert rule.passed is True
        assert "跳过" in rule.details

    async def test_vr_l1_01_skip_partial_data(self, db_session, project_id):
        """VR-L1-01 跳过: L1 有部分数据但期末缺失"""
        gate = ConsistencyGate(db_session)
        l1_data = {
            "l1_opening": "10000000.00",
            "l1_new_borrowings": "5000000.00",
            # l1_closing missing
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "L8": None, "L1": l1_data, "L3": None,
                "H9": None, "L5": None,
            }.get(code)
            checks = await gate.check_l_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "L1勾稽" in c.check_name)
        assert rule.passed is True
        assert "跳过" in rule.details


    # --- VR-L3-01: L3 期末 + 重分类 = 期初 + 新增 − 偿还 (warning) ---

    async def test_vr_l3_01_pass(self, db_session, project_id):
        """VR-L3-01 通过: L3 期末 + 重分类 = 期初 + 新增 − 偿还 (差异 = 0)"""
        gate = ConsistencyGate(db_session)
        # 期初=5000万, 新增=2000万, 偿还=1000万 → expected=6000万
        # 期末=5500万, 重分类=500万 → actual=6000万 → diff=0
        l3_data = {
            "l3_closing": "55000000.00",
            "l3_opening": "50000000.00",
            "l3_new_borrowings": "20000000.00",
            "l3_repayments": "10000000.00",
            "l3_reclassified_current": "5000000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "L8": None, "L1": None, "L3": l3_data,
                "H9": None, "L5": None,
            }.get(code)
            checks = await gate.check_l_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "L3勾稽" in c.check_name)
        assert rule.passed is True
        assert rule.severity == "warning"

    async def test_vr_l3_01_fail(self, db_session, project_id):
        """VR-L3-01 失败: 差异 > 1.0"""
        gate = ConsistencyGate(db_session)
        # expected = 5000万 + 2000万 − 1000万 = 6000万
        # actual = 5800万 + 500万 = 6300万；diff = 300万
        l3_data = {
            "l3_closing": "58000000.00",
            "l3_opening": "50000000.00",
            "l3_new_borrowings": "20000000.00",
            "l3_repayments": "10000000.00",
            "l3_reclassified_current": "5000000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "L8": None, "L1": None, "L3": l3_data,
                "H9": None, "L5": None,
            }.get(code)
            checks = await gate.check_l_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "L3勾稽" in c.check_name)
        assert rule.passed is False
        assert rule.severity == "warning"

    async def test_vr_l3_01_skip_l3_not_saved(self, db_session, project_id):
        """VR-L3-01 跳过: L3-1 审定表未保存"""
        gate = ConsistencyGate(db_session)
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "L8": None, "L1": None, "L3": None,
                "H9": None, "L5": None,
            }.get(code)
            checks = await gate.check_l_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "L3勾稽" in c.check_name)
        assert rule.passed is True
        assert "跳过" in rule.details

    async def test_vr_l3_01_is_warning_not_blocking(self, db_session, project_id):
        """VR-L3-01 验证: severity 是 warning 不是 blocking（不阻断签字）"""
        gate = ConsistencyGate(db_session)
        # 故意制造差异 → fail，但 severity=warning 不阻断
        l3_data = {
            "l3_closing": "99000000.00",
            "l3_opening": "50000000.00",
            "l3_new_borrowings": "20000000.00",
            "l3_repayments": "10000000.00",
            "l3_reclassified_current": "5000000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "L8": None, "L1": None, "L3": l3_data,
                "H9": None, "L5": None,
            }.get(code)
            checks = await gate.check_l_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "L3勾稽" in c.check_name)
        assert rule.passed is False
        assert rule.severity == "warning"
        # warning 不应阻断 overall
        result = ConsistencyResult(overall="pass", checks=checks)
        assert result.has_blocking_failures is False


# ---------------------------------------------------------------------------
# Test boundary conditions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestLCycleBoundaryConditions:
    """Test L 循环三角勾稽边界条件."""

    async def test_vr_l8_01_at_tolerance_boundary(self, db_session, project_id):
        """VR-L8-01 容差边界: 差异 = 0.99 应通过"""
        gate = ConsistencyGate(db_session)
        # expected = 50万 + 80万 + 20万 + 30万 = 180万；actual = 180万 + 0.99
        l8_data = {"l8_interest": "1800000.99"}
        l1_data = {"l1_interest": "500000.00"}
        l3_data = {"l3_interest": "800000.00"}
        h9_data = {"h9_lease_interest": "200000.00"}
        l5_data = {"l5_bond_interest": "300000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "L8": l8_data, "L1": l1_data, "L3": l3_data,
                "H9": h9_data, "L5": l5_data,
            }.get(code)
            checks = await gate.check_l_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "L8勾稽" in c.check_name)
        assert rule.passed is True

    async def test_vr_l8_01_just_above_tolerance(self, db_session, project_id):
        """VR-L8-01 容差刚超: 差异 = 1.0 应失败（formula: diff < 1.0）"""
        gate = ConsistencyGate(db_session)
        l8_data = {"l8_interest": "1800001.00"}
        l1_data = {"l1_interest": "500000.00"}
        l3_data = {"l3_interest": "800000.00"}
        h9_data = {"h9_lease_interest": "200000.00"}
        l5_data = {"l5_bond_interest": "300000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "L8": l8_data, "L1": l1_data, "L3": l3_data,
                "H9": h9_data, "L5": l5_data,
            }.get(code)
            checks = await gate.check_l_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "L8勾稽" in c.check_name)
        assert rule.passed is False

    async def test_vr_l1_01_at_tolerance_boundary(self, db_session, project_id):
        """VR-L1-01 容差边界: 差异 = 0.50 应通过"""
        gate = ConsistencyGate(db_session)
        # expected = 1000万 + 500万 − 300万 = 1200万；actual = 1200万 + 0.50
        l1_data = {
            "l1_closing": "12000000.50",
            "l1_opening": "10000000.00",
            "l1_new_borrowings": "5000000.00",
            "l1_repayments": "3000000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "L8": None, "L1": l1_data, "L3": None,
                "H9": None, "L5": None,
            }.get(code)
            checks = await gate.check_l_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "L1勾稽" in c.check_name)
        assert rule.passed is True

    async def test_skip_does_not_block_overall(self, db_session, project_id):
        """所有 L 规则 skip 时 ConsistencyResult 应仍为 pass"""
        gate = ConsistencyGate(db_session)
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock, return_value=None
        ):
            checks = await gate.check_l_cycle_triangle_reconciliation(project_id, 2025)

        # 3 条规则全部 skip 但 passed=True
        assert len(checks) == 3
        for c in checks:
            assert c.passed is True
        # 模拟 ConsistencyResult 不会被 L 阻断
        result = ConsistencyResult(overall="pass", checks=checks)
        assert result.has_blocking_failures is False


# ---------------------------------------------------------------------------
# Integration: run_all_checks includes L cycle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestLCycleIntegration:
    """Verify L cycle checks are included in run_all_checks."""

    async def test_run_all_checks_includes_l_cycle(self, db_session, project_id):
        """run_all_checks 包含 L 循环 3 条 VR 检查"""
        gate = ConsistencyGate(db_session)
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock, return_value=None
        ), patch.object(
            gate, "check_tb_balance", new_callable=AsyncMock,
            return_value=CheckItem(check_name="tb", passed=True, severity="blocking"),
        ), patch.object(
            gate, "check_bs_balance", new_callable=AsyncMock,
            return_value=CheckItem(check_name="bs", passed=True, severity="blocking"),
        ), patch.object(
            gate, "check_is_reconciliation", new_callable=AsyncMock,
            return_value=CheckItem(check_name="is", passed=True, severity="blocking"),
        ), patch.object(
            gate, "check_notes_completeness", new_callable=AsyncMock,
            return_value=CheckItem(check_name="notes", passed=True, severity="warning"),
        ), patch.object(
            gate, "check_data_freshness", new_callable=AsyncMock,
            return_value=CheckItem(check_name="fresh", passed=True, severity="warning"),
        ), patch.object(
            gate, "check_e1_cfs_reconciliation", new_callable=AsyncMock,
            return_value=[],
        ), patch.object(
            gate, "check_d4_revenue_reconciliation", new_callable=AsyncMock,
            return_value=[],
        ), patch.object(
            gate, "check_f5_f2_triangle_reconciliation", new_callable=AsyncMock,
            return_value=[],
        ), patch.object(
            gate, "check_h_cycle_triangle_reconciliation", new_callable=AsyncMock,
            return_value=[],
        ), patch.object(
            gate, "check_i_cycle_triangle_reconciliation", new_callable=AsyncMock,
            return_value=[],
        ), patch.object(
            gate, "check_g_cycle_triangle_reconciliation", new_callable=AsyncMock,
            return_value=[],
        ), patch.object(
            gate, "check_j_cycle_triangle_reconciliation", new_callable=AsyncMock,
            return_value=[],
        ), patch.object(
            gate, "check_k_cycle_triangle_reconciliation", new_callable=AsyncMock,
            return_value=[],
        ):
            result = await gate.run_all_checks(project_id, 2025)

        # L cycle produces 3 checks (all skip since _get_wp_parsed_data returns None)
        l_checks = [c for c in result.checks if "L" in c.check_name and "勾稽" in c.check_name]
        assert len(l_checks) == 3
        # All should be passed=True (skip mode)
        assert all(c.passed for c in l_checks)
        # Verify rule names cover L8/L1/L3
        joined = " ".join(c.check_name for c in l_checks)
        assert "L8勾稽" in joined
        assert "L1勾稽" in joined
        assert "L3勾稽" in joined

    async def test_run_all_checks_does_not_break_other_cycles(
        self, db_session, project_id
    ):
        """L 循环加入后 K 循环回归无影响"""
        gate = ConsistencyGate(db_session)
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock, return_value=None
        ):
            result = await gate.run_all_checks(project_id, 2025)

        # 应包含 K 循环 3 条 + L 循环 3 条 = 共 6 条 cycle 三角勾稽
        cycle_checks = [
            c for c in result.checks
            if "勾稽" in c.check_name and (
                "K8" in c.check_name or "K9" in c.check_name
                or "K11" in c.check_name
                or "L8" in c.check_name or "L1" in c.check_name
                or "L3" in c.check_name
            )
        ]
        assert len(cycle_checks) >= 6
