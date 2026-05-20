"""Tests for M 权益循环 2 条 VR (VR-M6-01 + VR-M2-01)

Validates: Requirements M-F3
- VR-M6-01: M6 期末 = 期初 + 净利润 − 盈余公积 − 股利 (blocking, tolerance=1.0)
  - 汇总类规则时机铁律: M6 + 至少 1 个来源 saved → 触发；全部来源未保存 → skip
- VR-M2-01: M2 期末 = 期初 + 增资 − 减资 (warning, tolerance=1.0)
  - 时机约束: M2-1 saved；M2-1 未保存 → skip

Spec: workpaper-m-equity-cycle / Sprint 1 / Task 1.2
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
# Test JSON structure (VR-M6-01 + VR-M2-01 entries exist)
# ---------------------------------------------------------------------------

class TestMValidationRulesJSON:
    """Test 2 条 VR JSON entries in m_cycle_validation_rules.json."""

    @pytest.fixture
    def rules_data(self):
        rules_path = (
            Path(__file__).parent.parent / "data" / "m_cycle_validation_rules.json"
        )
        with open(rules_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @pytest.fixture
    def m_rules(self, rules_data):
        return rules_data["rules"]

    def test_file_exists(self):
        rules_path = (
            Path(__file__).parent.parent / "data" / "m_cycle_validation_rules.json"
        )
        assert rules_path.exists(), "m_cycle_validation_rules.json missing"

    def test_two_m_rules_exist(self, m_rules):
        """2 条 VR-M6-01/M2-01 规则存在"""
        ids = sorted(r["rule_id"] for r in m_rules)
        assert ids == ["VR-M2-01", "VR-M6-01"]

    def test_vr_m6_01_blocking(self, m_rules):
        rule = next(r for r in m_rules if r["rule_id"] == "VR-M6-01")
        assert rule["severity"] == "blocking"
        assert rule["tolerance"] == 1.0
        assert rule["wp_code"] == "M6"

    def test_vr_m2_01_warning(self, m_rules):
        rule = next(r for r in m_rules if r["rule_id"] == "VR-M2-01")
        assert rule["severity"] == "warning"
        assert rule["tolerance"] == 1.0
        assert rule["wp_code"] == "M2"

    def test_vr_m6_01_has_summary_rule_timing(self, m_rules):
        """VR-M6-01 遵循汇总类规则时机铁律：required_any_of_subs 配置 PL/M5/M1"""
        rule = next(r for r in m_rules if r["rule_id"] == "VR-M6-01")
        assert "applies_when" in rule
        applies = rule["applies_when"]
        assert applies.get("required_main_wp") == "M6"
        any_subs = applies.get("required_any_of_subs", [])
        assert set(any_subs) >= {"PL", "M5", "M1"}

    def test_vr_m2_01_no_sub_dependencies(self, m_rules):
        """VR-M2-01 无外部来源依赖（仅 M2-1 自身）"""
        rule = next(r for r in m_rules if r["rule_id"] == "VR-M2-01")
        assert "applies_when" in rule
        applies = rule["applies_when"]
        assert applies.get("required_main_wp") == "M2"
        assert applies.get("required_any_of_subs") == []

    def test_rules_have_required_fields(self, m_rules):
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
        for rule in m_rules:
            missing = required_fields - set(rule.keys())
            assert not missing, f"Rule {rule['rule_id']} missing fields: {missing}"

    def test_rule_type_is_cross_reconciliation(self, m_rules):
        for rule in m_rules:
            assert rule["rule_type"] == "cross_reconciliation"


# ---------------------------------------------------------------------------
# Test formula evaluation logic — pass/fail/skip scenarios
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestMCycleTriangleLogic:
    """Test M 循环三角勾稽校验逻辑 — pass/fail/skip scenarios."""

    # --- VR-M6-01: M6 期末 = 期初 + 净利润 − 盈余公积 − 股利 ---

    async def test_vr_m6_01_pass(self, db_session, project_id):
        """VR-M6-01 通过: M6 期末 = 期初 + 净利润 − 盈余公积 − 股利 (差异 = 0)"""
        gate = ConsistencyGate(db_session)
        # 期末 = 500万 + 200万 − 30万 − 20万 = 650万
        m6_data = {"m6_closing": "6500000.00", "m6_opening": "5000000.00"}
        pl_data = {"net_profit": "2000000.00"}
        m5_data = {"surplus_reserve": "300000.00"}
        m1_data = {"dividends": "200000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "M6": m6_data, "M2": None, "PL": pl_data,
                "M5": m5_data, "M1": m1_data,
            }.get(code)
            checks = await gate.check_m_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "M6勾稽" in c.check_name)
        assert rule.passed is True
        assert rule.severity == "blocking"

    async def test_vr_m6_01_pass_within_tolerance(self, db_session, project_id):
        """VR-M6-01 通过: 差异 < 1.0 (tolerance boundary)"""
        gate = ConsistencyGate(db_session)
        # expected = 500万 + 200万 − 30万 − 20万 = 650万；actual = 650万 + 0.99 → pass
        m6_data = {"m6_closing": "6500000.99", "m6_opening": "5000000.00"}
        pl_data = {"net_profit": "2000000.00"}
        m5_data = {"surplus_reserve": "300000.00"}
        m1_data = {"dividends": "200000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "M6": m6_data, "M2": None, "PL": pl_data,
                "M5": m5_data, "M1": m1_data,
            }.get(code)
            checks = await gate.check_m_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "M6勾稽" in c.check_name)
        assert rule.passed is True

    async def test_vr_m6_01_fail_blocking(self, db_session, project_id):
        """VR-M6-01 失败 (blocking): 差异 >= 1.0"""
        gate = ConsistencyGate(db_session)
        # expected = 500万 + 200万 − 30万 − 20万 = 650万；actual = 660万；diff = 10万
        m6_data = {"m6_closing": "6600000.00", "m6_opening": "5000000.00"}
        pl_data = {"net_profit": "2000000.00"}
        m5_data = {"surplus_reserve": "300000.00"}
        m1_data = {"dividends": "200000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "M6": m6_data, "M2": None, "PL": pl_data,
                "M5": m5_data, "M1": m1_data,
            }.get(code)
            checks = await gate.check_m_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "M6勾稽" in c.check_name)
        assert rule.passed is False
        assert rule.severity == "blocking"

    async def test_vr_m6_01_fail_at_boundary(self, db_session, project_id):
        """VR-M6-01 失败: 差异恰好 = 1.0 (边界 — 不通过，因为 < 1.0 才通过)"""
        gate = ConsistencyGate(db_session)
        # expected = 500万 + 200万 − 30万 − 20万 = 650万；actual = 650万 + 1.0
        m6_data = {"m6_closing": "6500001.00", "m6_opening": "5000000.00"}
        pl_data = {"net_profit": "2000000.00"}
        m5_data = {"surplus_reserve": "300000.00"}
        m1_data = {"dividends": "200000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "M6": m6_data, "M2": None, "PL": pl_data,
                "M5": m5_data, "M1": m1_data,
            }.get(code)
            checks = await gate.check_m_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "M6勾稽" in c.check_name)
        assert rule.passed is False

    async def test_vr_m6_01_skip_all_sources_unsaved(self, db_session, project_id):
        """VR-M6-01 跳过: PL/M5/M1 全部未保存（汇总类规则时机铁律）"""
        gate = ConsistencyGate(db_session)
        m6_data = {"m6_closing": "6500000.00", "m6_opening": "5000000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "M6": m6_data, "M2": None, "PL": None,
                "M5": None, "M1": None,
            }.get(code)
            checks = await gate.check_m_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "M6勾稽" in c.check_name)
        assert rule.passed is True
        assert "跳过" in rule.details

    async def test_vr_m6_01_skip_m6_not_saved(self, db_session, project_id):
        """VR-M6-01 跳过: M6 审定数缺失"""
        gate = ConsistencyGate(db_session)
        pl_data = {"net_profit": "2000000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "M6": None, "M2": None, "PL": pl_data,
                "M5": None, "M1": None,
            }.get(code)
            checks = await gate.check_m_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "M6勾稽" in c.check_name)
        assert rule.passed is True
        assert "跳过" in rule.details

    async def test_vr_m6_01_partial_sources_triggers_check(self, db_session, project_id):
        """VR-M6-01 部分来源已保存: 仅 PL 已保存 → 仍触发校验"""
        gate = ConsistencyGate(db_session)
        # M6 期末 = 650万；期初 = 500万；仅 PL 净利润 = 200万
        # expected = 500万 + 200万 − 0 − 0 = 700万；diff = |650万 - 700万| = 50万 → fail
        m6_data = {"m6_closing": "6500000.00", "m6_opening": "5000000.00"}
        pl_data = {"net_profit": "2000000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "M6": m6_data, "M2": None, "PL": pl_data,
                "M5": None, "M1": None,
            }.get(code)
            checks = await gate.check_m_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "M6勾稽" in c.check_name)
        # 部分来源已保存 → 触发校验（不 skip）
        assert rule.severity == "blocking"
        # 差异 = |650万 - 700万| = 50万 > 1.0 → fail
        assert rule.passed is False

    # --- VR-M2-01: M2 期末 = 期初 + 增资 − 减资 ---

    async def test_vr_m2_01_pass(self, db_session, project_id):
        """VR-M2-01 通过: M2 期末 = 期初 + 增资 − 减资 (差异 = 0)"""
        gate = ConsistencyGate(db_session)
        # 期末 = 1000万 + 500万 − 200万 = 1300万
        m2_data = {
            "m2_closing": "13000000.00",
            "m2_opening": "10000000.00",
            "m2_capital_increase": "5000000.00",
            "m2_capital_decrease": "2000000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "M6": None, "M2": m2_data, "PL": None,
                "M5": None, "M1": None,
            }.get(code)
            checks = await gate.check_m_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "M2勾稽" in c.check_name)
        assert rule.passed is True
        assert rule.severity == "warning"

    async def test_vr_m2_01_pass_within_tolerance(self, db_session, project_id):
        """VR-M2-01 通过: 差异 < 1.0 (tolerance boundary)"""
        gate = ConsistencyGate(db_session)
        # expected = 1000万 + 500万 − 200万 = 1300万；actual = 1300万 + 0.50
        m2_data = {
            "m2_closing": "13000000.50",
            "m2_opening": "10000000.00",
            "m2_capital_increase": "5000000.00",
            "m2_capital_decrease": "2000000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "M6": None, "M2": m2_data, "PL": None,
                "M5": None, "M1": None,
            }.get(code)
            checks = await gate.check_m_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "M2勾稽" in c.check_name)
        assert rule.passed is True

    async def test_vr_m2_01_warn_when_drift_exceeds_tolerance(self, db_session, project_id):
        """VR-M2-01 警告 (warning): 差异 >= 1.0"""
        gate = ConsistencyGate(db_session)
        # expected = 1000万 + 500万 − 200万 = 1300万；actual = 1400万；diff = 100万
        m2_data = {
            "m2_closing": "14000000.00",
            "m2_opening": "10000000.00",
            "m2_capital_increase": "5000000.00",
            "m2_capital_decrease": "2000000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "M6": None, "M2": m2_data, "PL": None,
                "M5": None, "M1": None,
            }.get(code)
            checks = await gate.check_m_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "M2勾稽" in c.check_name)
        assert rule.passed is False
        assert rule.severity == "warning"

    async def test_vr_m2_01_fail_at_boundary(self, db_session, project_id):
        """VR-M2-01 失败: 差异恰好 = 1.0 (边界 — 不通过)"""
        gate = ConsistencyGate(db_session)
        # expected = 1000万 + 500万 − 200万 = 1300万；actual = 1300万 + 1.0
        m2_data = {
            "m2_closing": "13000001.00",
            "m2_opening": "10000000.00",
            "m2_capital_increase": "5000000.00",
            "m2_capital_decrease": "2000000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "M6": None, "M2": m2_data, "PL": None,
                "M5": None, "M1": None,
            }.get(code)
            checks = await gate.check_m_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "M2勾稽" in c.check_name)
        assert rule.passed is False

    async def test_vr_m2_01_skip_not_saved(self, db_session, project_id):
        """VR-M2-01 跳过: M2-1 审定表未保存"""
        gate = ConsistencyGate(db_session)
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "M6": None, "M2": None, "PL": None,
                "M5": None, "M1": None,
            }.get(code)
            checks = await gate.check_m_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "M2勾稽" in c.check_name)
        assert rule.passed is True
        assert "跳过" in rule.details

    async def test_vr_m2_01_skip_partial_data(self, db_session, project_id):
        """VR-M2-01 跳过: M2 仅有期末无期初"""
        gate = ConsistencyGate(db_session)
        m2_data = {"m2_closing": "13000000.00"}  # 无 m2_opening
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "M6": None, "M2": m2_data, "PL": None,
                "M5": None, "M1": None,
            }.get(code)
            checks = await gate.check_m_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "M2勾稽" in c.check_name)
        assert rule.passed is True
        assert "跳过" in rule.details

    # --- Combined: all data None → all skip ---

    async def test_all_none_returns_two_skip_checks(self, db_session, project_id):
        """全部底稿未保存 → 2 条规则全部 skip 但 passed=True"""
        gate = ConsistencyGate(db_session)
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock, return_value=None
        ):
            checks = await gate.check_m_cycle_triangle_reconciliation(project_id, 2025)

        # 2 条规则全部 skip 但 passed=True
        assert len(checks) == 2
        assert all(c.passed is True for c in checks)
        assert all("跳过" in c.details for c in checks)
