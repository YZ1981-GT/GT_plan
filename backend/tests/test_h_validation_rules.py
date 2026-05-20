"""Tests for H 固定资产循环 4 条 VR (VR-H1-01/02/03 + VR-H8-01)

Validates: Requirements H-F6
- VR-H1-01: 固定资产期末 = 期初 + 增加(H1-7) − 减少(H1-8) + H10处置 (blocking, tolerance=1.0)
- VR-H1-02: 累计折旧期末 = 期初 + 本期计提(H1-12) − 处置冲减(H10) (blocking, tolerance=1.0)
- VR-H8-01: 使用权资产期末 = 租赁负债期末 + 初始直接费用 − 激励 (blocking, tolerance=1.0)
- VR-H1-03: 平均折旧率波动 < 5% (warning, tolerance=0.05)

Spec: workpaper-h-fixed-assets-cycle / Sprint 2 / Task 2.12
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
# Test JSON structure (VR-H1-01~03 + VR-H8-01 entries exist and are correct)
# ---------------------------------------------------------------------------

class TestHValidationRulesJSON:
    """Test 4 条 VR JSON entries in h_cycle_validation_rules.json."""

    @pytest.fixture
    def rules_data(self):
        rules_path = (
            Path(__file__).parent.parent / "data" / "h_cycle_validation_rules.json"
        )
        with open(rules_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @pytest.fixture
    def h_rules(self, rules_data):
        return rules_data["rules"]

    def test_file_exists(self):
        rules_path = (
            Path(__file__).parent.parent / "data" / "h_cycle_validation_rules.json"
        )
        assert rules_path.exists(), "h_cycle_validation_rules.json missing"

    def test_four_h_rules_exist(self, h_rules):
        """4 条 VR-H1/H8 规则存在"""
        ids = sorted(r["rule_id"] for r in h_rules)
        assert ids == ["VR-H1-01", "VR-H1-02", "VR-H1-03", "VR-H8-01"]

    def test_vr_h1_01_blocking(self, h_rules):
        rule = next(r for r in h_rules if r["rule_id"] == "VR-H1-01")
        assert rule["severity"] == "blocking"
        assert rule["tolerance"] == 1.0
        assert rule["wp_code"] == "H1"

    def test_vr_h1_02_blocking(self, h_rules):
        rule = next(r for r in h_rules if r["rule_id"] == "VR-H1-02")
        assert rule["severity"] == "blocking"
        assert rule["tolerance"] == 1.0
        assert rule["wp_code"] == "H1"

    def test_vr_h8_01_blocking(self, h_rules):
        rule = next(r for r in h_rules if r["rule_id"] == "VR-H8-01")
        assert rule["severity"] == "blocking"
        assert rule["tolerance"] == 1.0
        assert rule["wp_code"] == "H8"

    def test_vr_h1_03_warning(self, h_rules):
        rule = next(r for r in h_rules if r["rule_id"] == "VR-H1-03")
        assert rule["severity"] == "warning"
        assert rule["tolerance"] == 0.05
        assert rule["wp_code"] == "H1"
        assert rule.get("cross_validation") == "cross_to_D5"

    def test_rules_have_required_fields(self, h_rules):
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
        for rule in h_rules:
            missing = required_fields - set(rule.keys())
            assert not missing, f"Rule {rule['rule_id']} missing fields: {missing}"

    def test_rule_type_is_cross_reconciliation(self, h_rules):
        for rule in h_rules:
            assert rule["rule_type"] == "cross_reconciliation"


# ---------------------------------------------------------------------------
# Test formula evaluation logic (mock data: pass/fail/skip scenarios)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestHCycleTriangleLogic:
    """Test H 循环三角勾稽校验逻辑 — pass/fail/skip scenarios."""

    # --- VR-H1-01 ---

    async def test_vr_h1_01_pass(self, db_session, project_id):
        """VR-H1-01 通过: closing = opening + additions - disposals + h10_disposal (差异 < 1.0)"""
        gate = ConsistencyGate(db_session)
        h1_data = {
            "fixed_asset_closing": "10000000.00",
            "fixed_asset_opening": "8000000.00",
            "fixed_asset_additions": "3000000.00",
            "fixed_asset_disposals": "1500000.00",
        }
        h10_data = {"disposal_original_cost": "500000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "H1": h1_data, "H8": None, "H9": None, "H10": h10_data
            }.get(code)
            checks = await gate.check_h_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "固定资产原值期末" in c.check_name)
        assert rule.passed is True
        assert rule.severity == "blocking"

    async def test_vr_h1_01_fail(self, db_session, project_id):
        """VR-H1-01 失败: 差异 > 1.0"""
        gate = ConsistencyGate(db_session)
        h1_data = {
            "fixed_asset_closing": "10000000.00",
            "fixed_asset_opening": "8000000.00",
            "fixed_asset_additions": "3000000.00",
            "fixed_asset_disposals": "500000.00",  # diff = 10M - (8M+3M-0.5M+0.5M) = -1M
        }
        h10_data = {"disposal_original_cost": "500000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "H1": h1_data, "H8": None, "H9": None, "H10": h10_data
            }.get(code)
            checks = await gate.check_h_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "固定资产原值期末" in c.check_name)
        assert rule.passed is False
        assert rule.severity == "blocking"

    async def test_vr_h1_01_skip(self, db_session, project_id):
        """VR-H1-01 数据缺失时跳过"""
        gate = ConsistencyGate(db_session)
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock, return_value=None
        ):
            checks = await gate.check_h_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "固定资产原值期末" in c.check_name)
        assert rule.passed is True
        assert "数据不完整" in rule.details

    # --- VR-H1-02 ---

    async def test_vr_h1_02_pass(self, db_session, project_id):
        """VR-H1-02 通过: dep_closing = dep_opening + current_provision - disposal_offset"""
        gate = ConsistencyGate(db_session)
        h1_data = {
            "depreciation_closing": "3000000.00",
            "depreciation_opening": "2000000.00",
            "current_depreciation": "1200000.00",
        }
        h10_data = {"disposal_depreciation_offset": "200000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "H1": h1_data, "H8": None, "H9": None, "H10": h10_data
            }.get(code)
            checks = await gate.check_h_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "累计折旧期末" in c.check_name)
        assert rule.passed is True
        assert rule.severity == "blocking"

    async def test_vr_h1_02_fail(self, db_session, project_id):
        """VR-H1-02 失败: 差异 > 1.0"""
        gate = ConsistencyGate(db_session)
        h1_data = {
            "depreciation_closing": "3500000.00",  # expected = 2M + 1.2M - 0.2M = 3M, diff = 500K
            "depreciation_opening": "2000000.00",
            "current_depreciation": "1200000.00",
        }
        h10_data = {"disposal_depreciation_offset": "200000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "H1": h1_data, "H8": None, "H9": None, "H10": h10_data
            }.get(code)
            checks = await gate.check_h_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "累计折旧期末" in c.check_name)
        assert rule.passed is False
        assert rule.severity == "blocking"

    async def test_vr_h1_02_skip(self, db_session, project_id):
        """VR-H1-02 数据缺失时跳过"""
        gate = ConsistencyGate(db_session)
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock, return_value=None
        ):
            checks = await gate.check_h_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "累计折旧期末" in c.check_name)
        assert rule.passed is True
        assert "数据不完整" in rule.details

    # --- VR-H8-01 ---

    async def test_vr_h8_01_pass(self, db_session, project_id):
        """VR-H8-01 通过: h8_closing = h9_closing + initial_direct_cost - incentive"""
        gate = ConsistencyGate(db_session)
        h8_data = {
            "right_of_use_closing": "5050000.00",
            "initial_direct_cost": "100000.00",
            "lease_incentive": "50000.00",
        }
        h9_data = {"lease_liability_closing": "5000000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "H1": None, "H8": h8_data, "H9": h9_data, "H10": None
            }.get(code)
            checks = await gate.check_h_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "使用权资产" in c.check_name)
        assert rule.passed is True
        assert rule.severity == "blocking"

    async def test_vr_h8_01_fail(self, db_session, project_id):
        """VR-H8-01 失败: 差异 > 1.0"""
        gate = ConsistencyGate(db_session)
        h8_data = {
            "right_of_use_closing": "6000000.00",  # expected = 5M + 0.1M - 0.05M = 5.05M, diff = 950K
            "initial_direct_cost": "100000.00",
            "lease_incentive": "50000.00",
        }
        h9_data = {"lease_liability_closing": "5000000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "H1": None, "H8": h8_data, "H9": h9_data, "H10": None
            }.get(code)
            checks = await gate.check_h_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "使用权资产" in c.check_name)
        assert rule.passed is False
        assert rule.severity == "blocking"

    async def test_vr_h8_01_skip(self, db_session, project_id):
        """VR-H8-01 数据缺失时跳过"""
        gate = ConsistencyGate(db_session)
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock, return_value=None
        ):
            checks = await gate.check_h_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "使用权资产" in c.check_name)
        assert rule.passed is True
        assert "数据不完整" in rule.details

    # --- VR-H1-03 ---

    async def test_vr_h1_03_pass(self, db_session, project_id):
        """VR-H1-03 通过: 折旧率波动 < 5%"""
        gate = ConsistencyGate(db_session)
        h1_data = {
            "current_dep_rate": "0.10",
            "prior_dep_rate": "0.12",  # diff = 0.02 < 0.05
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "H1": h1_data, "H8": None, "H9": None, "H10": None
            }.get(code)
            checks = await gate.check_h_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "折旧率波动" in c.check_name)
        assert rule.passed is True
        assert rule.severity == "warning"

    async def test_vr_h1_03_fail(self, db_session, project_id):
        """VR-H1-03 失败: 折旧率波动 >= 5%"""
        gate = ConsistencyGate(db_session)
        h1_data = {
            "current_dep_rate": "0.15",
            "prior_dep_rate": "0.08",  # diff = 0.07 > 0.05
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "H1": h1_data, "H8": None, "H9": None, "H10": None
            }.get(code)
            checks = await gate.check_h_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "折旧率波动" in c.check_name)
        assert rule.passed is False
        assert rule.severity == "warning"

    async def test_vr_h1_03_skip(self, db_session, project_id):
        """VR-H1-03 数据缺失时跳过"""
        gate = ConsistencyGate(db_session)
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock, return_value=None
        ):
            checks = await gate.check_h_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "折旧率波动" in c.check_name)
        assert rule.passed is True
        assert "数据不完整" in rule.details

    # --- Integration tests ---

    async def test_all_skip_when_no_data(self, db_session, project_id):
        """所有数据缺失时全部跳过 (passed=True), 长度=4"""
        gate = ConsistencyGate(db_session)
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock, return_value=None
        ):
            checks = await gate.check_h_cycle_triangle_reconciliation(project_id, 2025)

        assert len(checks) == 4
        for c in checks:
            assert c.passed is True

    async def test_blocking_rule_prevents_signoff(self, db_session, project_id):
        """VR-H1-01 blocking 失败时阻断签字"""
        gate = ConsistencyGate(db_session)
        h1_data = {
            "fixed_asset_closing": "10000000.00",
            "fixed_asset_opening": "8000000.00",
            "fixed_asset_additions": "3000000.00",
            "fixed_asset_disposals": "500000.00",
        }
        h10_data = {"disposal_original_cost": "500000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "H1": h1_data, "H8": None, "H9": None, "H10": h10_data
            }.get(code)
            checks = await gate.check_h_cycle_triangle_reconciliation(project_id, 2025)

        result = ConsistencyResult(overall="fail", checks=checks)
        assert result.has_blocking_failures is True

    async def test_warnings_do_not_block(self, db_session, project_id):
        """VR-H1-03 warning 失败不阻断签字"""
        checks = [
            CheckItem(
                check_name="H1勾稽:固定资产原值期末=期初+增加-减少+处置",
                passed=True,
                severity="blocking",
            ),
            CheckItem(
                check_name="H1勾稽:累计折旧期末=期初+计提-处置冲减",
                passed=True,
                severity="blocking",
            ),
            CheckItem(
                check_name="H8勾稽:使用权资产=租赁负债+直接费用-激励",
                passed=True,
                severity="blocking",
            ),
            CheckItem(
                check_name="H1勾稽:平均折旧率波动<5%",
                passed=False,
                severity="warning",
            ),
        ]
        result = ConsistencyResult(overall="pass", checks=checks)
        assert result.has_blocking_failures is False


# ---------------------------------------------------------------------------
# Test integration with run_all_checks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestHIntegrationWithRunAllChecks:
    """Verify check_h_cycle_triangle_reconciliation is wired into run_all_checks."""

    async def test_h_cycle_checks_included(self, db_session, project_id):
        """run_all_checks 包含 4 条 H 循环三角勾稽规则"""
        gate = ConsistencyGate(db_session)
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock, return_value=None
        ):
            result = await gate.run_all_checks(project_id, 2025)

        h_check_names = [
            c.check_name for c in result.checks if c.check_name.startswith("H")
        ]
        assert len(h_check_names) >= 4
        joined = " ".join(h_check_names)
        assert "固定资产原值期末" in joined
        assert "累计折旧期末" in joined
        assert "使用权资产" in joined
        assert "折旧率波动" in joined
