"""Tests for F5/F2 三角勾稽 4 条 VR (VR-F5-01~02 + VR-F2-01~02)

Validates: Requirements F-F6
- VR-F5-01: 营业成本 = 期初存货 + 本期采购 - 期末存货 (blocking, tolerance=1.0)
- VR-F5-02: 毛利率波动 < 5% (warning, tolerance=0.05, 与 VR-D4-03 交叉验证)
- VR-F2-01: 存货跌价准备计提率 vs 上年变动 < 3% (warning, tolerance=0.03)
- VR-F2-02: 存货周转天数 vs 行业均值差异 < 30 天 (warning, tolerance=30)

Spec: workpaper-f-purchase-inventory / Sprint 2 / Task 2.13
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
# Test JSON structure (VR-F5-01~02 + VR-F2-01~02 entries exist and are correct)
# ---------------------------------------------------------------------------

class TestFValidationRulesJSON:
    """Test 4 条 VR JSON entries in f_cycle_validation_rules.json."""

    @pytest.fixture
    def rules_data(self):
        rules_path = (
            Path(__file__).parent.parent / "data" / "f_cycle_validation_rules.json"
        )
        with open(rules_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @pytest.fixture
    def f_rules(self, rules_data):
        return rules_data["rules"]

    def test_file_exists(self):
        rules_path = (
            Path(__file__).parent.parent / "data" / "f_cycle_validation_rules.json"
        )
        assert rules_path.exists(), "f_cycle_validation_rules.json missing"

    def test_four_f_rules_exist(self, f_rules):
        """4 条 VR-F5/F2 规则存在"""
        ids = sorted(r["rule_id"] for r in f_rules)
        assert ids == ["VR-F2-01", "VR-F2-02", "VR-F5-01", "VR-F5-02"]

    def test_vr_f5_01_blocking(self, f_rules):
        rule = next(r for r in f_rules if r["rule_id"] == "VR-F5-01")
        assert rule["severity"] == "blocking"
        assert rule["tolerance"] == 1.0
        assert rule["wp_code"] == "F5"

    def test_vr_f5_02_warning(self, f_rules):
        rule = next(r for r in f_rules if r["rule_id"] == "VR-F5-02")
        assert rule["severity"] == "warning"
        assert rule["tolerance"] == 0.05
        # Cross-validation with VR-D4-03
        assert rule.get("cross_validation") == "VR-D4-03"

    def test_vr_f2_01_warning(self, f_rules):
        rule = next(r for r in f_rules if r["rule_id"] == "VR-F2-01")
        assert rule["severity"] == "warning"
        assert rule["tolerance"] == 0.03
        assert rule["wp_code"] == "F2"

    def test_vr_f2_02_warning(self, f_rules):
        rule = next(r for r in f_rules if r["rule_id"] == "VR-F2-02")
        assert rule["severity"] == "warning"
        assert rule["tolerance"] == 30
        assert rule["wp_code"] == "F2"

    def test_rules_have_required_fields(self, f_rules):
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
        for rule in f_rules:
            missing = required_fields - set(rule.keys())
            assert not missing, f"Rule {rule['rule_id']} missing fields: {missing}"

    def test_rule_type_is_cross_reconciliation(self, f_rules):
        for rule in f_rules:
            assert rule["rule_type"] == "cross_reconciliation"

    def test_vr_f5_01_sources(self, f_rules):
        """VR-F5-01 sources 包含 cost / opening / purchases / closing,涉及 F2+F5"""
        rule = next(r for r in f_rules if r["rule_id"] == "VR-F5-01")
        for key in ("cost", "opening", "purchases", "closing"):
            assert key in rule["sources"]
        # F5 -> cost; F2 -> opening/purchases/closing
        assert rule["sources"]["cost"]["wp"] == "F5"
        assert rule["sources"]["opening"]["wp"] == "F2"

    def test_vr_f5_02_cross_to_d4(self, f_rules):
        """VR-F5-02 sources 跨 D4 + F5"""
        rule = next(r for r in f_rules if r["rule_id"] == "VR-F5-02")
        wps = {src["wp"] for src in rule["sources"].values()}
        assert "D4" in wps
        assert "F5" in wps


# ---------------------------------------------------------------------------
# Test formula evaluation logic (mock data: pass/fail/skip scenarios)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestF5F2TriangleLogic:
    """Test F5/F2 三角勾稽校验逻辑 — pass/fail/skip scenarios."""

    async def test_vr_f5_01_pass(self, db_session, project_id):
        """VR-F5-01 通过: cost = opening + purchases - closing (差异 < 1.0)"""
        gate = ConsistencyGate(db_session)
        f5_data = {"cost_of_sales": "5000000.00"}
        f2_data = {
            "inventory_opening": "1000000.00",
            "purchases": "5500000.00",
            "inventory_closing": "1500000.50",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: (
                f5_data if code == "F5" else f2_data if code == "F2" else None
            )
            checks = await gate.check_f5_f2_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "营业成本=期初+采购-期末" in c.check_name)
        assert rule.passed is True
        assert rule.severity == "blocking"

    async def test_vr_f5_01_fail(self, db_session, project_id):
        """VR-F5-01 失败: 差异 > 1.0"""
        gate = ConsistencyGate(db_session)
        f5_data = {"cost_of_sales": "5000000.00"}
        f2_data = {
            "inventory_opening": "1000000.00",
            "purchases": "5500000.00",
            "inventory_closing": "1499000.00",  # diff = 1001 > 1.0
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: (
                f5_data if code == "F5" else f2_data if code == "F2" else None
            )
            checks = await gate.check_f5_f2_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "营业成本=期初+采购-期末" in c.check_name)
        assert rule.passed is False
        assert rule.severity == "blocking"

    async def test_vr_f5_01_skip_when_data_missing(self, db_session, project_id):
        """VR-F5-01 数据缺失时跳过 (passed=True, blocking)"""
        gate = ConsistencyGate(db_session)
        with patch.object(
            gate,
            "_get_wp_parsed_data",
            new_callable=AsyncMock,
            return_value=None,
        ):
            checks = await gate.check_f5_f2_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "营业成本=期初+采购-期末" in c.check_name)
        assert rule.passed is True  # Skipped, not failed
        assert "数据不完整" in rule.details

    async def test_vr_f5_02_pass(self, db_session, project_id):
        """VR-F5-02 通过: 毛利率波动 < 5%"""
        gate = ConsistencyGate(db_session)
        f5_data = {
            "current_gross_margin": "0.30",
            "prior_gross_margin": "0.32",  # diff = 0.02 < 0.05
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: (
                f5_data if code == "F5" else None
            )
            checks = await gate.check_f5_f2_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "毛利率波动" in c.check_name)
        assert rule.passed is True
        assert rule.severity == "warning"

    async def test_vr_f5_02_fail(self, db_session, project_id):
        """VR-F5-02 失败: 毛利率波动 >= 5%"""
        gate = ConsistencyGate(db_session)
        f5_data = {
            "current_gross_margin": "0.40",
            "prior_gross_margin": "0.30",  # diff = 0.10 > 0.05
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: (
                f5_data if code == "F5" else None
            )
            checks = await gate.check_f5_f2_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "毛利率波动" in c.check_name)
        assert rule.passed is False
        assert rule.severity == "warning"

    async def test_vr_f2_01_pass(self, db_session, project_id):
        """VR-F2-01 通过: 跌价准备计提率波动 < 3%"""
        gate = ConsistencyGate(db_session)
        f2_data = {
            "current_impairment_ratio": "0.05",
            "prior_impairment_ratio": "0.06",  # diff = 0.01 < 0.03
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: (
                f2_data if code == "F2" else None
            )
            checks = await gate.check_f5_f2_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "跌价准备计提率" in c.check_name)
        assert rule.passed is True
        assert rule.severity == "warning"

    async def test_vr_f2_01_fail(self, db_session, project_id):
        """VR-F2-01 失败: 计提率波动 >= 3%"""
        gate = ConsistencyGate(db_session)
        f2_data = {
            "current_impairment_ratio": "0.10",
            "prior_impairment_ratio": "0.05",  # diff = 0.05 > 0.03
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: (
                f2_data if code == "F2" else None
            )
            checks = await gate.check_f5_f2_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "跌价准备计提率" in c.check_name)
        assert rule.passed is False
        assert rule.severity == "warning"

    async def test_vr_f2_02_pass(self, db_session, project_id):
        """VR-F2-02 通过: 存货周转天数差异 < 30 天"""
        gate = ConsistencyGate(db_session)
        f2_data = {
            "turnover_days": "120",
            "industry_avg_days": "100",  # diff = 20 < 30
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: (
                f2_data if code == "F2" else None
            )
            checks = await gate.check_f5_f2_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "存货周转天数" in c.check_name)
        assert rule.passed is True
        assert rule.severity == "warning"

    async def test_vr_f2_02_fail(self, db_session, project_id):
        """VR-F2-02 失败: 周转天数差异 >= 30 天"""
        gate = ConsistencyGate(db_session)
        f2_data = {
            "turnover_days": "180",
            "industry_avg_days": "100",  # diff = 80 > 30
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: (
                f2_data if code == "F2" else None
            )
            checks = await gate.check_f5_f2_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "存货周转天数" in c.check_name)
        assert rule.passed is False
        assert rule.severity == "warning"

    async def test_all_skip_when_no_data(self, db_session, project_id):
        """所有数据缺失时全部跳过 (passed=True), 长度=4"""
        gate = ConsistencyGate(db_session)
        with patch.object(
            gate,
            "_get_wp_parsed_data",
            new_callable=AsyncMock,
            return_value=None,
        ):
            checks = await gate.check_f5_f2_triangle_reconciliation(project_id, 2025)

        assert len(checks) == 4
        for c in checks:
            assert c.passed is True

    async def test_blocking_rule_prevents_signoff(self, db_session, project_id):
        """VR-F5-01 blocking 失败时阻断签字"""
        gate = ConsistencyGate(db_session)
        f5_data = {"cost_of_sales": "5000000.00"}
        f2_data = {
            "inventory_opening": "1000000.00",
            "purchases": "5500000.00",
            "inventory_closing": "1499000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: (
                f5_data if code == "F5" else f2_data if code == "F2" else None
            )
            checks = await gate.check_f5_f2_triangle_reconciliation(project_id, 2025)

        result = ConsistencyResult(overall="fail", checks=checks)
        assert result.has_blocking_failures is True

    async def test_warnings_do_not_block(self, db_session, project_id):
        """VR-F5-02 / VR-F2-01 / VR-F2-02 warning 失败不阻断"""
        # Only warnings fail
        checks = [
            CheckItem(
                check_name="F5勾稽:营业成本=期初+采购-期末",
                passed=True,
                severity="blocking",
            ),
            CheckItem(
                check_name="F5勾稽:毛利率波动<5%(交叉VR-D4-03)",
                passed=False,
                severity="warning",
            ),
            CheckItem(
                check_name="F2勾稽:跌价准备计提率波动<3%",
                passed=False,
                severity="warning",
            ),
            CheckItem(
                check_name="F2勾稽:存货周转天数vs行业均值",
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
class TestIntegrationWithRunAllChecks:
    """Verify check_f5_f2_triangle_reconciliation is wired into run_all_checks."""

    async def test_f5_f2_checks_included(self, db_session, project_id):
        """run_all_checks 包含 4 条 F5/F2 三角勾稽规则"""
        gate = ConsistencyGate(db_session)
        # All other check sources empty -> they will skip; F triangle should
        # produce 4 entries either way.
        with patch.object(
            gate,
            "_get_wp_parsed_data",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await gate.run_all_checks(project_id, 2025)

        f_check_names = [
            c.check_name for c in result.checks if c.check_name.startswith("F")
        ]
        # Expect at least 4 F-prefixed checks (营业成本/毛利率/跌价/周转)
        assert len(f_check_names) >= 4
        joined = " ".join(f_check_names)
        assert "营业成本=期初+采购-期末" in joined
        assert "毛利率波动<5%" in joined
        assert "跌价准备计提率" in joined
        assert "存货周转天数" in joined
