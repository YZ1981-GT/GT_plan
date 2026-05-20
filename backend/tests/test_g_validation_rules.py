"""Tests for G 投资循环 4 条 VR (VR-G7-01 + VR-G11-01 + VR-G1-01 + VR-G14-01)

Validates: Requirements G-F6
- VR-G7-01: G7 权益法投资收益 = 净利润 × 持股比例 − 内部抵消 (blocking, tolerance=1.0)
  - 时机约束: shareholding_ratio=0 或缺失 → skip (passed=True, details="持股比例为零或权益法投资未保存，跳过")
- VR-G11-01: G11 投资收益 = G1+G4+G6+G7+G8 各子循环汇总 (blocking, tolerance=1.0)
  - 时机约束: G11 已保存且至少 1 个子循环已保存才触发 blocking, 全部子循环未保存 → skip
- VR-G1-01: G1 公允价值变动 = 期末公允价值 − 期初公允价值 (blocking, tolerance=1.0)
  - 时机约束: 数据缺失时跳过 (无 skip 业务逻辑, G1 内部勾稽)
- VR-G14-01: G14 信用减值损失 = G4 ECL 变动 + G6 ECL 变动 (blocking, tolerance=1.0)
  - 时机约束: G14 已保存且至少 1 个子循环已保存才触发 blocking, 全部子循环未保存 → skip

Spec: workpaper-g-investment-cycle / Sprint 2 / Task 2.14
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
# Test JSON structure (VR-G7-01 + VR-G11-01 + VR-G1-01 + VR-G14-01 entries exist)
# ---------------------------------------------------------------------------

class TestGValidationRulesJSON:
    """Test 4 条 VR JSON entries in g_cycle_validation_rules.json."""

    @pytest.fixture
    def rules_data(self):
        rules_path = (
            Path(__file__).parent.parent / "data" / "g_cycle_validation_rules.json"
        )
        with open(rules_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @pytest.fixture
    def g_rules(self, rules_data):
        return rules_data["rules"]

    def test_file_exists(self):
        rules_path = (
            Path(__file__).parent.parent / "data" / "g_cycle_validation_rules.json"
        )
        assert rules_path.exists(), "g_cycle_validation_rules.json missing"

    def test_four_g_rules_exist(self, g_rules):
        """4 条 VR-G1/G7/G11/G14 规则存在"""
        ids = sorted(r["rule_id"] for r in g_rules)
        assert ids == ["VR-G1-01", "VR-G11-01", "VR-G14-01", "VR-G7-01"]

    def test_vr_g7_01_blocking(self, g_rules):
        rule = next(r for r in g_rules if r["rule_id"] == "VR-G7-01")
        assert rule["severity"] == "blocking"
        assert rule["tolerance"] == 1.0
        assert rule["wp_code"] == "G7"

    def test_vr_g11_01_blocking(self, g_rules):
        rule = next(r for r in g_rules if r["rule_id"] == "VR-G11-01")
        assert rule["severity"] == "blocking"
        assert rule["tolerance"] == 1.0
        assert rule["wp_code"] == "G11"

    def test_vr_g11_01_has_trigger_condition(self, g_rules):
        """VR-G11-01 含 trigger_condition 标记 G11 + 至少 1 子循环都保存才触发"""
        rule = next(r for r in g_rules if r["rule_id"] == "VR-G11-01")
        assert rule.get("trigger_condition") == "G11_and_at_least_one_sub_saved"

    def test_vr_g1_01_blocking(self, g_rules):
        rule = next(r for r in g_rules if r["rule_id"] == "VR-G1-01")
        assert rule["severity"] == "blocking"
        assert rule["tolerance"] == 1.0
        assert rule["wp_code"] == "G1"

    def test_vr_g14_01_blocking(self, g_rules):
        rule = next(r for r in g_rules if r["rule_id"] == "VR-G14-01")
        assert rule["severity"] == "blocking"
        assert rule["tolerance"] == 1.0
        assert rule["wp_code"] == "G14"

    def test_vr_g14_01_has_trigger_condition(self, g_rules):
        """VR-G14-01 含 trigger_condition 标记 G14 + 至少 1 子循环都保存才触发"""
        rule = next(r for r in g_rules if r["rule_id"] == "VR-G14-01")
        assert rule.get("trigger_condition") == "G14_and_at_least_one_sub_saved"

    def test_rules_have_required_fields(self, g_rules):
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
        for rule in g_rules:
            missing = required_fields - set(rule.keys())
            assert not missing, f"Rule {rule['rule_id']} missing fields: {missing}"

    def test_rule_type_is_cross_reconciliation(self, g_rules):
        for rule in g_rules:
            assert rule["rule_type"] == "cross_reconciliation"


# ---------------------------------------------------------------------------
# Test formula evaluation logic — pass/fail/skip scenarios
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestGCycleTriangleLogic:
    """Test G 循环三角勾稽校验逻辑 — pass/fail/skip scenarios."""

    # --- VR-G7-01 ---

    async def test_vr_g7_01_pass(self, db_session, project_id):
        """VR-G7-01 通过: recognized = net_profit × ratio − offset (差异 < 1.0)"""
        gate = ConsistencyGate(db_session)
        # 1000万 × 0.30 − 50万 = 250万
        g7_data = {
            "recognized_income": "2500000.00",
            "investee_net_profit": "10000000.00",
            "shareholding_ratio": "0.30",
            "internal_offset": "500000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "G1": None, "G4": None, "G6": None, "G7": g7_data,
                "G8": None, "G11": None, "G14": None,
            }.get(code)
            checks = await gate.check_g_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "权益法投资收益" in c.check_name)
        assert rule.passed is True
        assert rule.severity == "blocking"

    async def test_vr_g7_01_fail(self, db_session, project_id):
        """VR-G7-01 失败: 差异 > 1.0"""
        gate = ConsistencyGate(db_session)
        # expected = 1000万 × 0.30 − 50万 = 250万, recognized=300万, diff=50万
        g7_data = {
            "recognized_income": "3000000.00",
            "investee_net_profit": "10000000.00",
            "shareholding_ratio": "0.30",
            "internal_offset": "500000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "G1": None, "G4": None, "G6": None, "G7": g7_data,
                "G8": None, "G11": None, "G14": None,
            }.get(code)
            checks = await gate.check_g_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "权益法投资收益" in c.check_name)
        assert rule.passed is False
        assert rule.severity == "blocking"

    async def test_vr_g7_01_skip_zero_shareholding_ratio(self, db_session, project_id):
        """VR-G7-01 跳过: shareholding_ratio=0 → skip (passed=True)"""
        gate = ConsistencyGate(db_session)
        g7_data = {
            "recognized_income": "2500000.00",
            "investee_net_profit": "10000000.00",
            "shareholding_ratio": "0",
            "internal_offset": "500000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "G1": None, "G4": None, "G6": None, "G7": g7_data,
                "G8": None, "G11": None, "G14": None,
            }.get(code)
            checks = await gate.check_g_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "权益法投资收益" in c.check_name)
        assert rule.passed is True
        assert "持股比例为零" in rule.details or "未保存" in rule.details

    async def test_vr_g7_01_skip_no_data(self, db_session, project_id):
        """VR-G7-01 跳过: G7 完全未保存 → skip"""
        gate = ConsistencyGate(db_session)
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock, return_value=None
        ):
            checks = await gate.check_g_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "权益法投资收益" in c.check_name)
        assert rule.passed is True

    async def test_vr_g7_01_boundary_within_tolerance(self, db_session, project_id):
        """VR-G7-01 边界: 差异 = 0.5 (< 1.0 通过)"""
        gate = ConsistencyGate(db_session)
        g7_data = {
            "recognized_income": "2500000.50",  # diff = 0.50 < 1.0
            "investee_net_profit": "10000000.00",
            "shareholding_ratio": "0.30",
            "internal_offset": "500000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "G1": None, "G4": None, "G6": None, "G7": g7_data,
                "G8": None, "G11": None, "G14": None,
            }.get(code)
            checks = await gate.check_g_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "权益法投资收益" in c.check_name)
        assert rule.passed is True

    # --- VR-G11-01 ---

    async def test_vr_g11_01_pass(self, db_session, project_id):
        """VR-G11-01 通过: G11 = G1 + G4 + G6 + G7 + G8"""
        gate = ConsistencyGate(db_session)
        g11_data = {"g11_total": "10000000.00"}
        g1_data = {"g1_income": "2000000.00"}
        g4_data = {"g4_interest": "1500000.00"}
        g6_data = {"g6_interest": "1000000.00"}
        g7_data = {"g7_income": "3500000.00"}
        g8_data = {"g8_disposal": "2000000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "G1": g1_data, "G4": g4_data, "G6": g6_data, "G7": g7_data,
                "G8": g8_data, "G11": g11_data, "G14": None,
            }.get(code)
            checks = await gate.check_g_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "投资收益=G1+G4+G6+G7+G8" in c.check_name)
        assert rule.passed is True
        assert rule.severity == "blocking"

    async def test_vr_g11_01_fail(self, db_session, project_id):
        """VR-G11-01 失败: G11 总额与子循环汇总差异 > 1.0"""
        gate = ConsistencyGate(db_session)
        # expected = 2 + 1.5 + 1 + 3.5 + 2 = 10M; G11 = 12M; diff = 2M
        g11_data = {"g11_total": "12000000.00"}
        g1_data = {"g1_income": "2000000.00"}
        g4_data = {"g4_interest": "1500000.00"}
        g6_data = {"g6_interest": "1000000.00"}
        g7_data = {"g7_income": "3500000.00"}
        g8_data = {"g8_disposal": "2000000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "G1": g1_data, "G4": g4_data, "G6": g6_data, "G7": g7_data,
                "G8": g8_data, "G11": g11_data, "G14": None,
            }.get(code)
            checks = await gate.check_g_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "投资收益=G1+G4+G6+G7+G8" in c.check_name)
        assert rule.passed is False
        assert rule.severity == "blocking"

    async def test_vr_g11_01_skip_no_subs_saved(self, db_session, project_id):
        """VR-G11-01 跳过: G11 已保存但全部子循环 (G1/G4/G6/G7/G8) 未保存"""
        gate = ConsistencyGate(db_session)
        g11_data = {"g11_total": "10000000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "G1": None, "G4": None, "G6": None, "G7": None,
                "G8": None, "G11": g11_data, "G14": None,
            }.get(code)
            checks = await gate.check_g_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "投资收益=G1+G4+G6+G7+G8" in c.check_name)
        assert rule.passed is True
        assert "子循环底稿未保存" in rule.details

    async def test_vr_g11_01_skip_g11_not_saved(self, db_session, project_id):
        """VR-G11-01 跳过: G11 未保存但子循环已保存 → skip"""
        gate = ConsistencyGate(db_session)
        g1_data = {"g1_income": "2000000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "G1": g1_data, "G4": None, "G6": None, "G7": None,
                "G8": None, "G11": None, "G14": None,
            }.get(code)
            checks = await gate.check_g_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "投资收益=G1+G4+G6+G7+G8" in c.check_name)
        assert rule.passed is True
        assert "未保存" in rule.details

    async def test_vr_g11_01_pass_with_partial_subs_filled(self, db_session, project_id):
        """VR-G11-01 通过: 仅 1 子循环已保存 (其余视为 0), 等式仍成立"""
        gate = ConsistencyGate(db_session)
        # 仅 G7 = 3500000, 其余子循环 None (视为 0); G11 = 3500000
        g11_data = {"g11_total": "3500000.00"}
        g7_data = {"g7_income": "3500000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "G1": None, "G4": None, "G6": None, "G7": g7_data,
                "G8": None, "G11": g11_data, "G14": None,
            }.get(code)
            checks = await gate.check_g_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "投资收益=G1+G4+G6+G7+G8" in c.check_name)
        assert rule.passed is True

    # --- VR-G1-01 ---

    async def test_vr_g1_01_pass(self, db_session, project_id):
        """VR-G1-01 通过: fv_change = fv_closing − fv_opening"""
        gate = ConsistencyGate(db_session)
        g1_data = {
            "fv_change": "500000.00",
            "fv_closing": "5500000.00",
            "fv_opening": "5000000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "G1": g1_data, "G4": None, "G6": None, "G7": None,
                "G8": None, "G11": None, "G14": None,
            }.get(code)
            checks = await gate.check_g_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "公允价值变动" in c.check_name)
        assert rule.passed is True
        assert rule.severity == "blocking"

    async def test_vr_g1_01_pass_negative_change(self, db_session, project_id):
        """VR-G1-01 通过: 公允价值下降 (负变动)"""
        gate = ConsistencyGate(db_session)
        g1_data = {
            "fv_change": "-300000.00",
            "fv_closing": "4700000.00",
            "fv_opening": "5000000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "G1": g1_data, "G4": None, "G6": None, "G7": None,
                "G8": None, "G11": None, "G14": None,
            }.get(code)
            checks = await gate.check_g_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "公允价值变动" in c.check_name)
        assert rule.passed is True

    async def test_vr_g1_01_fail(self, db_session, project_id):
        """VR-G1-01 失败: 差异 > 1.0"""
        gate = ConsistencyGate(db_session)
        # expected = 5500000 - 5000000 = 500000; fv_change = 700000; diff = 200000
        g1_data = {
            "fv_change": "700000.00",
            "fv_closing": "5500000.00",
            "fv_opening": "5000000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "G1": g1_data, "G4": None, "G6": None, "G7": None,
                "G8": None, "G11": None, "G14": None,
            }.get(code)
            checks = await gate.check_g_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "公允价值变动" in c.check_name)
        assert rule.passed is False
        assert rule.severity == "blocking"

    async def test_vr_g1_01_skip_data_missing(self, db_session, project_id):
        """VR-G1-01 跳过: G1 关键字段缺失"""
        gate = ConsistencyGate(db_session)
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock, return_value=None
        ):
            checks = await gate.check_g_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "公允价值变动" in c.check_name)
        assert rule.passed is True
        assert "数据不完整" in rule.details

    async def test_vr_g1_01_skip_partial_field_missing(self, db_session, project_id):
        """VR-G1-01 跳过: G1 部分字段缺失 (fv_opening 缺失)"""
        gate = ConsistencyGate(db_session)
        g1_data = {
            "fv_change": "500000.00",
            "fv_closing": "5500000.00",
            # fv_opening 缺失
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "G1": g1_data, "G4": None, "G6": None, "G7": None,
                "G8": None, "G11": None, "G14": None,
            }.get(code)
            checks = await gate.check_g_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "公允价值变动" in c.check_name)
        assert rule.passed is True
        assert "数据不完整" in rule.details

    # --- VR-G14-01 ---

    async def test_vr_g14_01_pass(self, db_session, project_id):
        """VR-G14-01 通过: G14 = G4 ECL 变动 + G6 ECL 变动"""
        gate = ConsistencyGate(db_session)
        g14_data = {"g14_total": "800000.00"}
        g4_data = {"g4_ecl_change": "500000.00"}
        g6_data = {"g6_ecl_change": "300000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "G1": None, "G4": g4_data, "G6": g6_data, "G7": None,
                "G8": None, "G11": None, "G14": g14_data,
            }.get(code)
            checks = await gate.check_g_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "信用减值损失" in c.check_name)
        assert rule.passed is True
        assert rule.severity == "blocking"

    async def test_vr_g14_01_fail(self, db_session, project_id):
        """VR-G14-01 失败: 差异 > 1.0"""
        gate = ConsistencyGate(db_session)
        # expected = 500000 + 300000 = 800000; G14 = 1000000; diff = 200000
        g14_data = {"g14_total": "1000000.00"}
        g4_data = {"g4_ecl_change": "500000.00"}
        g6_data = {"g6_ecl_change": "300000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "G1": None, "G4": g4_data, "G6": g6_data, "G7": None,
                "G8": None, "G11": None, "G14": g14_data,
            }.get(code)
            checks = await gate.check_g_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "信用减值损失" in c.check_name)
        assert rule.passed is False
        assert rule.severity == "blocking"

    async def test_vr_g14_01_skip_no_subs_saved(self, db_session, project_id):
        """VR-G14-01 跳过: G14 已保存但 G4/G6 全部未保存"""
        gate = ConsistencyGate(db_session)
        g14_data = {"g14_total": "800000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "G1": None, "G4": None, "G6": None, "G7": None,
                "G8": None, "G11": None, "G14": g14_data,
            }.get(code)
            checks = await gate.check_g_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "信用减值损失" in c.check_name)
        assert rule.passed is True
        assert "子循环底稿未保存" in rule.details

    async def test_vr_g14_01_skip_g14_not_saved(self, db_session, project_id):
        """VR-G14-01 跳过: G14 未保存但 G4 已保存"""
        gate = ConsistencyGate(db_session)
        g4_data = {"g4_ecl_change": "500000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "G1": None, "G4": g4_data, "G6": None, "G7": None,
                "G8": None, "G11": None, "G14": None,
            }.get(code)
            checks = await gate.check_g_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "信用减值损失" in c.check_name)
        assert rule.passed is True
        assert "未保存" in rule.details

    async def test_vr_g14_01_pass_partial_sub_saved(self, db_session, project_id):
        """VR-G14-01 通过: 仅 G6 已保存 (G4 视为 0), 等式成立"""
        gate = ConsistencyGate(db_session)
        g14_data = {"g14_total": "300000.00"}
        g6_data = {"g6_ecl_change": "300000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "G1": None, "G4": None, "G6": g6_data, "G7": None,
                "G8": None, "G11": None, "G14": g14_data,
            }.get(code)
            checks = await gate.check_g_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "信用减值损失" in c.check_name)
        assert rule.passed is True

    # --- Integration tests ---

    async def test_all_skip_when_no_data(self, db_session, project_id):
        """所有数据缺失时全部跳过 (passed=True), 长度=4"""
        gate = ConsistencyGate(db_session)
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock, return_value=None
        ):
            checks = await gate.check_g_cycle_triangle_reconciliation(project_id, 2025)

        assert len(checks) == 4
        for c in checks:
            assert c.passed is True

    async def test_all_blocking_severity(self, db_session, project_id):
        """4 条 G 循环规则全部 severity=blocking"""
        gate = ConsistencyGate(db_session)
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock, return_value=None
        ):
            checks = await gate.check_g_cycle_triangle_reconciliation(project_id, 2025)

        for c in checks:
            assert c.severity == "blocking"

    async def test_all_four_rules_returned(self, db_session, project_id):
        """check_g_cycle_triangle_reconciliation 始终返回 4 条规则结果"""
        gate = ConsistencyGate(db_session)
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock, return_value=None
        ):
            checks = await gate.check_g_cycle_triangle_reconciliation(project_id, 2025)

        assert len(checks) == 4
        joined = " ".join(c.check_name for c in checks)
        assert "权益法投资收益" in joined
        assert "投资收益=G1+G4+G6+G7+G8" in joined
        assert "公允价值变动" in joined
        assert "信用减值损失" in joined

    async def test_blocking_rule_prevents_signoff(self, db_session, project_id):
        """VR-G1-01 blocking 失败时阻断签字"""
        gate = ConsistencyGate(db_session)
        g1_data = {
            "fv_change": "1000000.00",  # expected = 500000, diff = 500000 (>>1.0)
            "fv_closing": "5500000.00",
            "fv_opening": "5000000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "G1": g1_data, "G4": None, "G6": None, "G7": None,
                "G8": None, "G11": None, "G14": None,
            }.get(code)
            checks = await gate.check_g_cycle_triangle_reconciliation(project_id, 2025)

        result = ConsistencyResult(overall="fail", checks=checks)
        assert result.has_blocking_failures is True


# ---------------------------------------------------------------------------
# Test integration with run_all_checks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestGIntegrationWithRunAllChecks:
    """Verify check_g_cycle_triangle_reconciliation is wired into run_all_checks."""

    async def test_g_cycle_checks_included(self, db_session, project_id):
        """run_all_checks 包含 4 条 G 循环三角勾稽规则"""
        gate = ConsistencyGate(db_session)
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock, return_value=None
        ):
            result = await gate.run_all_checks(project_id, 2025)

        g_check_names = [
            c.check_name for c in result.checks if c.check_name.startswith("G")
        ]
        assert len(g_check_names) >= 4
        joined = " ".join(g_check_names)
        assert "权益法投资收益" in joined
        assert "投资收益=G1+G4+G6+G7+G8" in joined
        assert "公允价值变动" in joined
        assert "信用减值损失" in joined

    async def test_g_blocking_failure_propagates_to_overall(
        self, db_session, project_id
    ):
        """G 循环 blocking 失败时 overall=fail"""
        gate = ConsistencyGate(db_session)
        g1_data = {
            "fv_change": "9999999.00",  # 差异远超 1.0
            "fv_closing": "5500000.00",
            "fv_opening": "5000000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: (
                g1_data if code == "G1" else None
            )
            result = await gate.run_all_checks(project_id, 2025)

        assert result.overall == "fail"
        assert result.has_blocking_failures is True
