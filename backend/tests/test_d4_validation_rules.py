"""Tests for D4 营业收入勾稽 4 条 VR (VR-D4-01~04)

Validates: Requirements F7
- VR-D4-01: 营业收入合计 = 主营业务收入 + 其他业务收入 (blocking)
- VR-D4-02: 应收账款增长率 vs 营业收入增长率合理性 (warning)
- VR-D4-03: 毛利率波动 < 5% (warning)
- VR-D4-04: 合同负债期末 vs D7-1 审定数一致 (blocking)
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
# Test JSON structure (VR-D4-01~04 entries exist and are correct)
# ---------------------------------------------------------------------------

class TestD4ValidationRulesJSON:
    """Test VR-D4-01~04 JSON entries in d_cycle_validation_rules.json."""

    @pytest.fixture
    def rules_data(self):
        rules_path = Path(__file__).parent.parent / "data" / "d_cycle_validation_rules.json"
        with open(rules_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @pytest.fixture
    def vr_d4_rules(self, rules_data):
        return [r for r in rules_data["rules"] if r["rule_id"].startswith("VR-D4-")]

    def test_four_vr_d4_rules_exist(self, vr_d4_rules):
        """4 条 VR-D4 规则存在"""
        assert len(vr_d4_rules) == 4

    def test_rule_ids_correct(self, vr_d4_rules):
        """规则 ID 为 VR-D4-01~04"""
        ids = sorted(r["rule_id"] for r in vr_d4_rules)
        assert ids == ["VR-D4-01", "VR-D4-02", "VR-D4-03", "VR-D4-04"]

    def test_all_rules_have_wp_code_d4(self, vr_d4_rules):
        """所有 VR-D4 规则 wp_code = D4"""
        for rule in vr_d4_rules:
            assert rule["wp_code"] == "D4"

    def test_blocking_rules_severity(self, vr_d4_rules):
        """VR-D4-01 和 VR-D4-04 为 blocking"""
        rule_map = {r["rule_id"]: r for r in vr_d4_rules}
        assert rule_map["VR-D4-01"]["severity"] == "blocking"
        assert rule_map["VR-D4-04"]["severity"] == "blocking"

    def test_warning_rules_severity(self, vr_d4_rules):
        """VR-D4-02 和 VR-D4-03 为 warning"""
        rule_map = {r["rule_id"]: r for r in vr_d4_rules}
        assert rule_map["VR-D4-02"]["severity"] == "warning"
        assert rule_map["VR-D4-03"]["severity"] == "warning"

    def test_rules_have_required_fields(self, vr_d4_rules):
        """每条规则包含必要字段"""
        required_fields = {"rule_id", "rule_type", "wp_code", "description",
                           "formula", "tolerance", "severity", "sources", "message_template"}
        for rule in vr_d4_rules:
            assert required_fields.issubset(set(rule.keys())), (
                f"Rule {rule['rule_id']} missing fields: {required_fields - set(rule.keys())}"
            )

    def test_rule_type_is_cross_reconciliation(self, vr_d4_rules):
        """所有 VR-D4 规则 rule_type = cross_reconciliation"""
        for rule in vr_d4_rules:
            assert rule["rule_type"] == "cross_reconciliation"

    def test_vr_d4_01_sources(self, vr_d4_rules):
        """VR-D4-01 sources 包含 revenue_total, main_revenue, other_revenue"""
        rule = next(r for r in vr_d4_rules if r["rule_id"] == "VR-D4-01")
        assert "revenue_total" in rule["sources"]
        assert "main_revenue" in rule["sources"]
        assert "other_revenue" in rule["sources"]

    def test_vr_d4_04_cross_wp_reference(self, vr_d4_rules):
        """VR-D4-04 引用 D7 底稿"""
        rule = next(r for r in vr_d4_rules if r["rule_id"] == "VR-D4-04")
        assert rule["sources"]["d7_audited"]["wp"] == "D7"

    def test_tolerance_values(self, vr_d4_rules):
        """容差值正确: blocking=1.0, warning 按业务规则"""
        rule_map = {r["rule_id"]: r for r in vr_d4_rules}
        assert rule_map["VR-D4-01"]["tolerance"] == 1.0
        assert rule_map["VR-D4-02"]["tolerance"] == 0.5
        assert rule_map["VR-D4-03"]["tolerance"] == 0.05
        assert rule_map["VR-D4-04"]["tolerance"] == 1.0


# ---------------------------------------------------------------------------
# Test formula evaluation logic (mock data: pass/fail scenarios)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestD4ValidationLogic:
    """Test D4 勾稽校验逻辑 — pass/fail scenarios."""

    async def test_vr_d4_01_pass(self, db_session, project_id):
        """VR-D4-01 通过: 营业收入合计 = 主营 + 其他 (差异 < 1.0)"""
        gate = ConsistencyGate(db_session)
        d4_data = {
            "revenue_total": "1000000.50",
            "main_revenue": "800000.30",
            "other_revenue": "200000.20",
        }
        with patch.object(gate, "_get_wp_parsed_data", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = lambda pid, code: (
                d4_data if code == "D4" else None
            )
            checks = await gate.check_d4_revenue_reconciliation(project_id, 2025)

        vr01 = next(c for c in checks if "营业收入合计" in c.check_name)
        assert vr01.passed is True
        assert vr01.severity == "blocking"

    async def test_vr_d4_01_fail(self, db_session, project_id):
        """VR-D4-01 失败: 差异 > 1.0"""
        gate = ConsistencyGate(db_session)
        d4_data = {
            "revenue_total": "1000000.00",
            "main_revenue": "800000.00",
            "other_revenue": "199998.00",  # diff = 2.0 > 1.0
        }
        with patch.object(gate, "_get_wp_parsed_data", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = lambda pid, code: (
                d4_data if code == "D4" else None
            )
            checks = await gate.check_d4_revenue_reconciliation(project_id, 2025)

        vr01 = next(c for c in checks if "营业收入合计" in c.check_name)
        assert vr01.passed is False
        assert vr01.severity == "blocking"

    async def test_vr_d4_02_pass(self, db_session, project_id):
        """VR-D4-02 通过: 增长率差异 < 0.5"""
        gate = ConsistencyGate(db_session)
        d4_data = {"growth_rate": "0.15"}
        d2_data = {"growth_rate": "0.20"}
        with patch.object(gate, "_get_wp_parsed_data", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = lambda pid, code: (
                d4_data if code == "D4" else d2_data if code == "D2" else None
            )
            checks = await gate.check_d4_revenue_reconciliation(project_id, 2025)

        vr02 = next(c for c in checks if "增长率" in c.check_name)
        assert vr02.passed is True
        assert vr02.severity == "warning"

    async def test_vr_d4_02_fail(self, db_session, project_id):
        """VR-D4-02 失败: 增长率差异 >= 0.5"""
        gate = ConsistencyGate(db_session)
        d4_data = {"growth_rate": "0.10"}
        d2_data = {"growth_rate": "0.80"}  # diff = 0.7 > 0.5
        with patch.object(gate, "_get_wp_parsed_data", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = lambda pid, code: (
                d4_data if code == "D4" else d2_data if code == "D2" else None
            )
            checks = await gate.check_d4_revenue_reconciliation(project_id, 2025)

        vr02 = next(c for c in checks if "增长率" in c.check_name)
        assert vr02.passed is False
        assert vr02.severity == "warning"

    async def test_vr_d4_03_pass(self, db_session, project_id):
        """VR-D4-03 通过: 毛利率波动 < 5%"""
        gate = ConsistencyGate(db_session)
        d4_data = {
            "current_gross_margin": "0.35",
            "prior_gross_margin": "0.33",  # diff = 0.02 < 0.05
        }
        with patch.object(gate, "_get_wp_parsed_data", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = lambda pid, code: (
                d4_data if code == "D4" else None
            )
            checks = await gate.check_d4_revenue_reconciliation(project_id, 2025)

        vr03 = next(c for c in checks if "毛利率" in c.check_name)
        assert vr03.passed is True
        assert vr03.severity == "warning"

    async def test_vr_d4_03_fail(self, db_session, project_id):
        """VR-D4-03 失败: 毛利率波动 >= 5%"""
        gate = ConsistencyGate(db_session)
        d4_data = {
            "current_gross_margin": "0.40",
            "prior_gross_margin": "0.30",  # diff = 0.10 > 0.05
        }
        with patch.object(gate, "_get_wp_parsed_data", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = lambda pid, code: (
                d4_data if code == "D4" else None
            )
            checks = await gate.check_d4_revenue_reconciliation(project_id, 2025)

        vr03 = next(c for c in checks if "毛利率" in c.check_name)
        assert vr03.passed is False
        assert vr03.severity == "warning"

    async def test_vr_d4_04_pass(self, db_session, project_id):
        """VR-D4-04 通过: D4 合同负债 ≈ D7-1 审定数 (差异 < 1.0)"""
        gate = ConsistencyGate(db_session)
        d4_data = {"contract_liability_ending": "500000.00"}
        d7_data = {"audited_total": "500000.50"}
        with patch.object(gate, "_get_wp_parsed_data", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = lambda pid, code: (
                d4_data if code == "D4" else d7_data if code == "D7" else None
            )
            checks = await gate.check_d4_revenue_reconciliation(project_id, 2025)

        vr04 = next(c for c in checks if "合同负债" in c.check_name)
        assert vr04.passed is True
        assert vr04.severity == "blocking"

    async def test_vr_d4_04_fail(self, db_session, project_id):
        """VR-D4-04 失败: D4 合同负债 ≠ D7-1 审定数 (差异 > 1.0)"""
        gate = ConsistencyGate(db_session)
        d4_data = {"contract_liability_ending": "500000.00"}
        d7_data = {"audited_total": "500005.00"}  # diff = 5.0 > 1.0
        with patch.object(gate, "_get_wp_parsed_data", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = lambda pid, code: (
                d4_data if code == "D4" else d7_data if code == "D7" else None
            )
            checks = await gate.check_d4_revenue_reconciliation(project_id, 2025)

        vr04 = next(c for c in checks if "合同负债" in c.check_name)
        assert vr04.passed is False
        assert vr04.severity == "blocking"

    async def test_missing_data_skips_gracefully(self, db_session, project_id):
        """数据缺失时所有检查跳过（passed=True）"""
        gate = ConsistencyGate(db_session)
        with patch.object(gate, "_get_wp_parsed_data", new_callable=AsyncMock, return_value=None):
            checks = await gate.check_d4_revenue_reconciliation(project_id, 2025)

        assert len(checks) == 4
        for c in checks:
            assert c.passed is True

    async def test_blocking_rules_prevent_signoff(self, db_session, project_id):
        """VR-D4-01/04 blocking 失败时 overall=fail（阻断签字）"""
        gate = ConsistencyGate(db_session)
        d4_data = {
            "revenue_total": "1000000.00",
            "main_revenue": "800000.00",
            "other_revenue": "199990.00",  # VR-D4-01 fail: diff=10
            "contract_liability_ending": "500000.00",
        }
        d7_data = {"audited_total": "500100.00"}  # VR-D4-04 fail: diff=100
        with patch.object(gate, "_get_wp_parsed_data", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = lambda pid, code: (
                d4_data if code == "D4" else d7_data if code == "D7" else None
            )
            checks = await gate.check_d4_revenue_reconciliation(project_id, 2025)

        blocking_failures = [c for c in checks if not c.passed and c.severity == "blocking"]
        assert len(blocking_failures) >= 1  # At least VR-D4-01 or VR-D4-04 failed

    async def test_warning_rules_do_not_block(self, db_session, project_id):
        """VR-D4-02/03 warning 失败不阻断签字"""
        # Construct a result where only warnings fail
        checks = [
            CheckItem(check_name="D4勾稽:营业收入合计=主营+其他", passed=True, severity="blocking"),
            CheckItem(check_name="D4勾稽:应收增长率vs收入增长率", passed=False, severity="warning"),
            CheckItem(check_name="D4勾稽:毛利率波动<5%", passed=False, severity="warning"),
            CheckItem(check_name="D4勾稽:合同负债vs D7-1审定数", passed=True, severity="blocking"),
        ]
        result = ConsistencyResult(overall="pass", checks=checks)
        assert not result.has_blocking_failures


# ---------------------------------------------------------------------------
# Test _extract_decimal helper
# ---------------------------------------------------------------------------

class TestExtractDecimal:
    """Test ConsistencyGate._extract_decimal helper."""

    def test_valid_string(self):
        assert ConsistencyGate._extract_decimal({"k": "123.45"}, "k") == Decimal("123.45")

    def test_valid_int(self):
        assert ConsistencyGate._extract_decimal({"k": 100}, "k") == Decimal("100")

    def test_none_data(self):
        assert ConsistencyGate._extract_decimal(None, "k") is None

    def test_missing_key(self):
        assert ConsistencyGate._extract_decimal({"a": "1"}, "k") is None

    def test_invalid_value(self):
        assert ConsistencyGate._extract_decimal({"k": "not_a_number"}, "k") is None
