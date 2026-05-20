"""Tests for J 职工薪酬循环 3 条 VR (VR-J1-01 + VR-J1-02 + VR-J1-03)

Validates: Requirements J-F3
- VR-J1-01: 应付职工薪酬期末 = 期初 + 计提(J1-6) − 实发(J1-7) (blocking, tolerance=1.0)
  - 时机约束: J1-1 AND (J1-6 OR J1-7) saved; 数据不完整 → skip
- VR-J1-02: 薪酬费用率年度波动 < 5% (warning, tolerance=0.05)
  - 时机约束: J1-4 saved AND PREV available; 无上年数据 → skip
- VR-J1-03: 薪酬分配合计 = D5 + K8 + K9 + F2 (blocking, tolerance=1.0)
  - 时机约束: J1-7 AND at least 1 target saved; skip_if_all_targets_missing=true
  - 汇总类规则时机铁律: D5/K8/K9/F2 全部未保存 → skip 不 blocking

Spec: workpaper-j-payroll-cycle / Sprint 1 / Task 1.4
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
# Test JSON structure (VR-J1-01 + VR-J1-02 + VR-J1-03 entries exist)
# ---------------------------------------------------------------------------

class TestJValidationRulesJSON:
    """Test 3 条 VR JSON entries in j_cycle_validation_rules.json."""

    @pytest.fixture
    def rules_data(self):
        rules_path = (
            Path(__file__).parent.parent / "data" / "j_cycle_validation_rules.json"
        )
        with open(rules_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @pytest.fixture
    def j_rules(self, rules_data):
        return rules_data["rules"]

    def test_file_exists(self):
        rules_path = (
            Path(__file__).parent.parent / "data" / "j_cycle_validation_rules.json"
        )
        assert rules_path.exists(), "j_cycle_validation_rules.json missing"

    def test_three_j_rules_exist(self, j_rules):
        """3 条 VR-J1-01/02/03 规则存在"""
        ids = sorted(r["rule_id"] for r in j_rules)
        assert ids == ["VR-J1-01", "VR-J1-02", "VR-J1-03"]

    def test_vr_j1_01_blocking(self, j_rules):
        rule = next(r for r in j_rules if r["rule_id"] == "VR-J1-01")
        assert rule["severity"] == "blocking"
        assert rule["tolerance"] == 1.0
        assert rule["wp_code"] == "J1"

    def test_vr_j1_02_warning(self, j_rules):
        rule = next(r for r in j_rules if r["rule_id"] == "VR-J1-02")
        assert rule["severity"] == "warning"
        assert rule["tolerance"] == 0.05
        assert rule["wp_code"] == "J1"

    def test_vr_j1_03_blocking_with_skip(self, j_rules):
        rule = next(r for r in j_rules if r["rule_id"] == "VR-J1-03")
        assert rule["severity"] == "blocking"
        assert rule["tolerance"] == 1.0
        assert rule["wp_code"] == "J1"
        assert rule.get("skip_if_all_targets_missing") is True

    def test_rules_have_required_fields(self, j_rules):
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
        for rule in j_rules:
            missing = required_fields - set(rule.keys())
            assert not missing, f"Rule {rule['rule_id']} missing fields: {missing}"

    def test_rule_type_is_cross_reconciliation(self, j_rules):
        for rule in j_rules:
            assert rule["rule_type"] == "cross_reconciliation"


# ---------------------------------------------------------------------------
# Test formula evaluation logic — pass/fail/skip scenarios (9 tests minimum)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestJCycleTriangleLogic:
    """Test J 循环三角勾稽校验逻辑 — pass/fail/skip scenarios."""

    # --- VR-J1-01: 应付职工薪酬期末 = 期初 + 计提 − 实发 ---

    async def test_vr_j1_01_pass(self, db_session, project_id):
        """VR-J1-01 通过: 期末 = 期初 + 计提 − 实发 (差异 = 0)"""
        gate = ConsistencyGate(db_session)
        # 期末 = 500万 + 1200万 − 1100万 = 600万
        j1_data = {
            "payroll_closing": "6000000.00",
            "payroll_opening": "5000000.00",
            "payroll_accrued": "12000000.00",
            "payroll_paid": "11000000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "J1": j1_data, "D5": None, "K8": None, "K9": None, "F2": None,
            }.get(code)
            checks = await gate.check_j_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "期末=期初+计提-实发" in c.check_name)
        assert rule.passed is True
        assert rule.severity == "blocking"

    async def test_vr_j1_01_fail(self, db_session, project_id):
        """VR-J1-01 失败: 差异 > 1.0"""
        gate = ConsistencyGate(db_session)
        # expected = 500万 + 1200万 − 1100万 = 600万; actual = 700万; diff = 100万
        j1_data = {
            "payroll_closing": "7000000.00",
            "payroll_opening": "5000000.00",
            "payroll_accrued": "12000000.00",
            "payroll_paid": "11000000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "J1": j1_data, "D5": None, "K8": None, "K9": None, "F2": None,
            }.get(code)
            checks = await gate.check_j_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "期末=期初+计提-实发" in c.check_name)
        assert rule.passed is False
        assert rule.severity == "blocking"

    async def test_vr_j1_01_skip_incomplete_data(self, db_session, project_id):
        """VR-J1-01 跳过: J1 数据不完整 (缺少期末)"""
        gate = ConsistencyGate(db_session)
        j1_data = {
            "payroll_opening": "5000000.00",
            "payroll_accrued": "12000000.00",
            # payroll_closing missing
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "J1": j1_data, "D5": None, "K8": None, "K9": None, "F2": None,
            }.get(code)
            checks = await gate.check_j_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "期末=期初+计提-实发" in c.check_name)
        assert rule.passed is True
        assert "跳过" in rule.details

    # --- VR-J1-02: 薪酬费用率年度波动 < 5% ---

    async def test_vr_j1_02_pass(self, db_session, project_id):
        """VR-J1-02 通过: 波动 < 5% (本年 0.30 vs 上年 0.29, 波动 ≈ 3.4%)"""
        gate = ConsistencyGate(db_session)
        j1_data = {
            "payroll_expense_rate_current": "0.30",
            "payroll_expense_rate_prev": "0.29",
            # VR-J1-01 fields to avoid interference
            "payroll_closing": "6000000.00",
            "payroll_opening": "5000000.00",
            "payroll_accrued": "12000000.00",
            "payroll_paid": "11000000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "J1": j1_data, "D5": None, "K8": None, "K9": None, "F2": None,
            }.get(code)
            checks = await gate.check_j_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "费用率" in c.check_name)
        assert rule.passed is True
        assert rule.severity == "warning"

    async def test_vr_j1_02_fail(self, db_session, project_id):
        """VR-J1-02 失败: 波动 > 5% (本年 0.40 vs 上年 0.30, 波动 ≈ 33%)"""
        gate = ConsistencyGate(db_session)
        j1_data = {
            "payroll_expense_rate_current": "0.40",
            "payroll_expense_rate_prev": "0.30",
            "payroll_closing": "6000000.00",
            "payroll_opening": "5000000.00",
            "payroll_accrued": "12000000.00",
            "payroll_paid": "11000000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "J1": j1_data, "D5": None, "K8": None, "K9": None, "F2": None,
            }.get(code)
            checks = await gate.check_j_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "费用率" in c.check_name)
        assert rule.passed is False
        assert rule.severity == "warning"

    async def test_vr_j1_02_skip_no_prev_data(self, db_session, project_id):
        """VR-J1-02 跳过: 无上年数据"""
        gate = ConsistencyGate(db_session)
        j1_data = {
            "payroll_expense_rate_current": "0.30",
            # payroll_expense_rate_prev missing
            "payroll_closing": "6000000.00",
            "payroll_opening": "5000000.00",
            "payroll_accrued": "12000000.00",
            "payroll_paid": "11000000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "J1": j1_data, "D5": None, "K8": None, "K9": None, "F2": None,
            }.get(code)
            checks = await gate.check_j_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "费用率" in c.check_name)
        assert rule.passed is True
        assert "跳过" in rule.details

    # --- VR-J1-03: 薪酬分配合计 = D5 + K8 + K9 + F2 ---

    async def test_vr_j1_03_pass(self, db_session, project_id):
        """VR-J1-03 通过: 分配合计 = D5 + K8 + K9 + F2 (差异 = 0)"""
        gate = ConsistencyGate(db_session)
        j1_data = {
            "payroll_allocation_total": "10000000.00",
            "payroll_closing": "6000000.00",
            "payroll_opening": "5000000.00",
            "payroll_accrued": "12000000.00",
            "payroll_paid": "11000000.00",
        }
        d5_data = {"d5_payroll": "3000000.00"}
        k8_data = {"k8_payroll": "2000000.00"}
        k9_data = {"k9_payroll": "4000000.00"}
        f2_data = {"f2_payroll": "1000000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "J1": j1_data, "D5": d5_data, "K8": k8_data,
                "K9": k9_data, "F2": f2_data,
            }.get(code)
            checks = await gate.check_j_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "分配合计" in c.check_name)
        assert rule.passed is True
        assert rule.severity == "blocking"

    async def test_vr_j1_03_fail(self, db_session, project_id):
        """VR-J1-03 失败: 分配合计与汇总差异 > 1.0"""
        gate = ConsistencyGate(db_session)
        # expected = 3M + 2M + 4M + 1M = 10M; actual = 12M; diff = 2M
        j1_data = {
            "payroll_allocation_total": "12000000.00",
            "payroll_closing": "6000000.00",
            "payroll_opening": "5000000.00",
            "payroll_accrued": "12000000.00",
            "payroll_paid": "11000000.00",
        }
        d5_data = {"d5_payroll": "3000000.00"}
        k8_data = {"k8_payroll": "2000000.00"}
        k9_data = {"k9_payroll": "4000000.00"}
        f2_data = {"f2_payroll": "1000000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "J1": j1_data, "D5": d5_data, "K8": k8_data,
                "K9": k9_data, "F2": f2_data,
            }.get(code)
            checks = await gate.check_j_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "分配合计" in c.check_name)
        assert rule.passed is False
        assert rule.severity == "blocking"

    async def test_vr_j1_03_skip_all_targets_missing(self, db_session, project_id):
        """VR-J1-03 跳过: D5/K8/K9/F2 全部未保存 → skip (汇总类规则时机铁律)"""
        gate = ConsistencyGate(db_session)
        j1_data = {
            "payroll_allocation_total": "10000000.00",
            "payroll_closing": "6000000.00",
            "payroll_opening": "5000000.00",
            "payroll_accrued": "12000000.00",
            "payroll_paid": "11000000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "J1": j1_data, "D5": None, "K8": None, "K9": None, "F2": None,
            }.get(code)
            checks = await gate.check_j_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "分配合计" in c.check_name)
        assert rule.passed is True
        assert "跳过" in rule.details

    async def test_vr_j1_03_partial_targets_triggers_check(self, db_session, project_id):
        """VR-J1-03 部分目标已保存: 仅 K8 已保存 → 仍触发 blocking 校验"""
        gate = ConsistencyGate(db_session)
        # 只有 K8 已保存 (2M), 其余 None → expected = 0+2M+0+0 = 2M
        # total_allocation = 10M → diff = 8M → fail
        j1_data = {
            "payroll_allocation_total": "10000000.00",
            "payroll_closing": "6000000.00",
            "payroll_opening": "5000000.00",
            "payroll_accrued": "12000000.00",
            "payroll_paid": "11000000.00",
        }
        k8_data = {"k8_payroll": "2000000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "J1": j1_data, "D5": None, "K8": k8_data, "K9": None, "F2": None,
            }.get(code)
            checks = await gate.check_j_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "分配合计" in c.check_name)
        # 部分目标已保存 → 触发校验（不 skip）
        assert rule.severity == "blocking"
        # 差异 = |10M - 2M| = 8M > 1.0 → fail
        assert rule.passed is False

    async def test_vr_j1_03_skip_j1_7_not_saved(self, db_session, project_id):
        """VR-J1-03 跳过: J1-7 未保存 (payroll_allocation_total 缺失)"""
        gate = ConsistencyGate(db_session)
        j1_data = {
            # payroll_allocation_total missing
            "payroll_closing": "6000000.00",
            "payroll_opening": "5000000.00",
            "payroll_accrued": "12000000.00",
            "payroll_paid": "11000000.00",
        }
        d5_data = {"d5_payroll": "3000000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "J1": j1_data, "D5": d5_data, "K8": None, "K9": None, "F2": None,
            }.get(code)
            checks = await gate.check_j_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "分配合计" in c.check_name)
        assert rule.passed is True
        assert "跳过" in rule.details


# ---------------------------------------------------------------------------
# Integration: run_all_checks includes J cycle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestJCycleIntegration:
    """Verify J cycle checks are included in run_all_checks."""

    async def test_run_all_checks_includes_j_cycle(self, db_session, project_id):
        """run_all_checks 包含 J 循环 3 条 VR 检查"""
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
        ):
            result = await gate.run_all_checks(project_id, 2025)

        # J cycle produces 3 checks (all skip since _get_wp_parsed_data returns None)
        j_checks = [c for c in result.checks if "J1" in c.check_name]
        assert len(j_checks) == 3
        # All should be passed=True (skip mode)
        assert all(c.passed for c in j_checks)
