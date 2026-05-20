"""Tests for K 管理循环 3 条 VR (VR-K8-01 + VR-K9-01 + VR-K11-01)

Validates: Requirements K-F3
- VR-K8-01: K8 销售费用 = K8-2 明细合计（薪酬+折旧+其他） (blocking, tolerance=1.0)
  - 时机约束: K8-1 AND K8-2 saved；K8-2 未保存 → skip
- VR-K9-01: K9 管理费用 = K9-2 明细合计（薪酬+折旧+其他） (blocking, tolerance=1.0)
  - 时机约束: K9-1 AND K9-2 saved；K9-2 未保存 → skip
- VR-K11-01: K11 资产减值损失 = H1-14 + I3 + G14 + F2 (warning, tolerance=1.0)
  - 汇总类规则时机铁律: K11 + 至少 1 个来源 saved → 触发；全部来源未保存 → skip

Spec: workpaper-k-admin-cycle / Sprint 1 / Task 1.4
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
# Test JSON structure (VR-K8-01 + VR-K9-01 + VR-K11-01 entries exist)
# ---------------------------------------------------------------------------

class TestKValidationRulesJSON:
    """Test 3 条 VR JSON entries in k_cycle_validation_rules.json."""

    @pytest.fixture
    def rules_data(self):
        rules_path = (
            Path(__file__).parent.parent / "data" / "k_cycle_validation_rules.json"
        )
        with open(rules_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @pytest.fixture
    def k_rules(self, rules_data):
        return rules_data["rules"]

    def test_file_exists(self):
        rules_path = (
            Path(__file__).parent.parent / "data" / "k_cycle_validation_rules.json"
        )
        assert rules_path.exists(), "k_cycle_validation_rules.json missing"

    def test_three_k_rules_exist(self, k_rules):
        """3 条 VR-K8-01/K9-01/K11-01 规则存在"""
        ids = sorted(r["rule_id"] for r in k_rules)
        assert ids == ["VR-K11-01", "VR-K8-01", "VR-K9-01"]

    def test_vr_k8_01_blocking(self, k_rules):
        rule = next(r for r in k_rules if r["rule_id"] == "VR-K8-01")
        assert rule["severity"] == "blocking"
        assert rule["tolerance"] == 1.0
        assert rule["wp_code"] == "K8"

    def test_vr_k9_01_blocking(self, k_rules):
        rule = next(r for r in k_rules if r["rule_id"] == "VR-K9-01")
        assert rule["severity"] == "blocking"
        assert rule["tolerance"] == 1.0
        assert rule["wp_code"] == "K9"

    def test_vr_k11_01_warning_with_skip(self, k_rules):
        rule = next(r for r in k_rules if r["rule_id"] == "VR-K11-01")
        assert rule["severity"] == "warning"
        assert rule["tolerance"] == 1.0
        assert rule["wp_code"] == "K11"
        # 汇总类时机铁律：required_any_of_subs 至少配置 H1/I3/G14/F2 一项
        assert "applies_when" in rule
        applies = rule["applies_when"]
        assert applies.get("required_main_wp") == "K11"
        any_subs = applies.get("required_any_of_subs", [])
        assert set(any_subs) >= {"H1", "I3", "G14", "F2"}

    def test_rules_have_required_fields(self, k_rules):
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
        for rule in k_rules:
            missing = required_fields - set(rule.keys())
            assert not missing, f"Rule {rule['rule_id']} missing fields: {missing}"

    def test_rule_type_is_cross_reconciliation(self, k_rules):
        for rule in k_rules:
            assert rule["rule_type"] == "cross_reconciliation"


# ---------------------------------------------------------------------------
# Test formula evaluation logic — pass/fail/skip scenarios
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestKCycleTriangleLogic:
    """Test K 循环三角勾稽校验逻辑 — pass/fail/skip scenarios."""

    # --- VR-K8-01: K8 销售费用 = K8-2 明细 ---

    async def test_vr_k8_01_pass(self, db_session, project_id):
        """VR-K8-01 通过: K8 = 薪酬 + 折旧 + 其他 (差异 = 0)"""
        gate = ConsistencyGate(db_session)
        # K8 = 100万 + 50万 + 200万 = 350万
        k8_data = {
            "k8_total": "3500000.00",
            "k8_payroll": "1000000.00",
            "k8_depreciation": "500000.00",
            "k8_other": "2000000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "K8": k8_data, "K9": None, "K11": None,
                "H1": None, "I3": None, "G14": None, "F2": None,
            }.get(code)
            checks = await gate.check_k_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "K8勾稽" in c.check_name)
        assert rule.passed is True
        assert rule.severity == "blocking"

    async def test_vr_k8_01_fail(self, db_session, project_id):
        """VR-K8-01 失败: 差异 > 1.0"""
        gate = ConsistencyGate(db_session)
        # expected = 100万 + 50万 + 200万 = 350万；actual = 400万；diff = 50万
        k8_data = {
            "k8_total": "4000000.00",
            "k8_payroll": "1000000.00",
            "k8_depreciation": "500000.00",
            "k8_other": "2000000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "K8": k8_data, "K9": None, "K11": None,
                "H1": None, "I3": None, "G14": None, "F2": None,
            }.get(code)
            checks = await gate.check_k_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "K8勾稽" in c.check_name)
        assert rule.passed is False
        assert rule.severity == "blocking"

    async def test_vr_k8_01_skip_k8_2_not_saved(self, db_session, project_id):
        """VR-K8-01 跳过: K8-2 明细未保存（薪酬/折旧/其他全部缺失）"""
        gate = ConsistencyGate(db_session)
        k8_data = {
            "k8_total": "3500000.00",
            # k8_payroll/k8_depreciation/k8_other all missing
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "K8": k8_data, "K9": None, "K11": None,
                "H1": None, "I3": None, "G14": None, "F2": None,
            }.get(code)
            checks = await gate.check_k_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "K8勾稽" in c.check_name)
        assert rule.passed is True
        assert "跳过" in rule.details

    async def test_vr_k8_01_skip_k8_total_missing(self, db_session, project_id):
        """VR-K8-01 跳过: K8 审定数缺失"""
        gate = ConsistencyGate(db_session)
        k8_data = {
            # k8_total missing
            "k8_payroll": "1000000.00",
            "k8_depreciation": "500000.00",
            "k8_other": "2000000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "K8": k8_data, "K9": None, "K11": None,
                "H1": None, "I3": None, "G14": None, "F2": None,
            }.get(code)
            checks = await gate.check_k_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "K8勾稽" in c.check_name)
        assert rule.passed is True
        assert "跳过" in rule.details

    # --- VR-K9-01: K9 管理费用 = K9-2 明细 ---

    async def test_vr_k9_01_pass(self, db_session, project_id):
        """VR-K9-01 通过: K9 = 薪酬 + 折旧 + 其他 (差异 = 0)"""
        gate = ConsistencyGate(db_session)
        # K9 = 200万 + 80万 + 120万 = 400万
        k9_data = {
            "k9_total": "4000000.00",
            "k9_payroll": "2000000.00",
            "k9_depreciation": "800000.00",
            "k9_other": "1200000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "K8": None, "K9": k9_data, "K11": None,
                "H1": None, "I3": None, "G14": None, "F2": None,
            }.get(code)
            checks = await gate.check_k_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "K9勾稽" in c.check_name)
        assert rule.passed is True
        assert rule.severity == "blocking"

    async def test_vr_k9_01_fail(self, db_session, project_id):
        """VR-K9-01 失败: 差异 > 1.0"""
        gate = ConsistencyGate(db_session)
        # expected = 200万 + 80万 + 120万 = 400万；actual = 500万；diff = 100万
        k9_data = {
            "k9_total": "5000000.00",
            "k9_payroll": "2000000.00",
            "k9_depreciation": "800000.00",
            "k9_other": "1200000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "K8": None, "K9": k9_data, "K11": None,
                "H1": None, "I3": None, "G14": None, "F2": None,
            }.get(code)
            checks = await gate.check_k_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "K9勾稽" in c.check_name)
        assert rule.passed is False
        assert rule.severity == "blocking"

    async def test_vr_k9_01_skip_k9_2_not_saved(self, db_session, project_id):
        """VR-K9-01 跳过: K9-2 明细未保存"""
        gate = ConsistencyGate(db_session)
        k9_data = {
            "k9_total": "4000000.00",
            # k9_payroll/k9_depreciation/k9_other all missing
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "K8": None, "K9": k9_data, "K11": None,
                "H1": None, "I3": None, "G14": None, "F2": None,
            }.get(code)
            checks = await gate.check_k_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "K9勾稽" in c.check_name)
        assert rule.passed is True
        assert "跳过" in rule.details

    # --- VR-K11-01: K11 资产减值汇总（汇总类时机铁律） ---

    async def test_vr_k11_01_pass(self, db_session, project_id):
        """VR-K11-01 通过: K11 = H1 + I3 + G + F2 (差异 = 0)"""
        gate = ConsistencyGate(db_session)
        # K11 = 30万 + 20万 + 10万 + 40万 = 100万
        k11_data = {"k11_total": "1000000.00"}
        h1_data = {"h1_impairment": "300000.00"}
        i3_data = {"i3_impairment": "200000.00"}
        g14_data = {"g_ecl": "100000.00"}
        f2_data = {"f2_impairment": "400000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "K8": None, "K9": None, "K11": k11_data,
                "H1": h1_data, "I3": i3_data, "G14": g14_data, "F2": f2_data,
            }.get(code)
            checks = await gate.check_k_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "K11勾稽" in c.check_name)
        assert rule.passed is True
        assert rule.severity == "warning"

    async def test_vr_k11_01_fail(self, db_session, project_id):
        """VR-K11-01 失败: 汇总差异 > 1.0"""
        gate = ConsistencyGate(db_session)
        # expected = 30万 + 20万 + 10万 + 40万 = 100万；actual = 150万；diff = 50万
        k11_data = {"k11_total": "1500000.00"}
        h1_data = {"h1_impairment": "300000.00"}
        i3_data = {"i3_impairment": "200000.00"}
        g14_data = {"g_ecl": "100000.00"}
        f2_data = {"f2_impairment": "400000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "K8": None, "K9": None, "K11": k11_data,
                "H1": h1_data, "I3": i3_data, "G14": g14_data, "F2": f2_data,
            }.get(code)
            checks = await gate.check_k_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "K11勾稽" in c.check_name)
        assert rule.passed is False
        assert rule.severity == "warning"

    async def test_vr_k11_01_skip_all_sources_missing(self, db_session, project_id):
        """VR-K11-01 跳过: H1/I3/G14/F2 全部未保存（汇总类规则时机铁律）

        这是 VR-K11-01 的核心铁律 — 当 K11 已保存但所有来源底稿未保存时，
        必须 skip 不触发 warning，避免 K11 先保存时误提示。
        """
        gate = ConsistencyGate(db_session)
        k11_data = {"k11_total": "1000000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "K8": None, "K9": None, "K11": k11_data,
                "H1": None, "I3": None, "G14": None, "F2": None,
            }.get(code)
            checks = await gate.check_k_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "K11勾稽" in c.check_name)
        assert rule.passed is True
        assert "跳过" in rule.details

    async def test_vr_k11_01_partial_sources_triggers_check(
        self, db_session, project_id
    ):
        """VR-K11-01 部分来源已保存: 仅 H1 已保存 → 仍触发校验"""
        gate = ConsistencyGate(db_session)
        # K11 = 100万；仅 H1 已保存 = 30万；差异 = 70万 → fail (warning)
        k11_data = {"k11_total": "1000000.00"}
        h1_data = {"h1_impairment": "300000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "K8": None, "K9": None, "K11": k11_data,
                "H1": h1_data, "I3": None, "G14": None, "F2": None,
            }.get(code)
            checks = await gate.check_k_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "K11勾稽" in c.check_name)
        # 部分来源已保存 → 触发校验（不 skip）
        assert rule.severity == "warning"
        # 差异 = |100万 - 30万| = 70万 > 1.0 → fail
        assert rule.passed is False

    async def test_vr_k11_01_skip_k11_not_saved(self, db_session, project_id):
        """VR-K11-01 跳过: K11 未保存（即使来源已保存）"""
        gate = ConsistencyGate(db_session)
        # K11 未保存（k11_total 缺失），但 H1/I3 已保存
        h1_data = {"h1_impairment": "300000.00"}
        i3_data = {"i3_impairment": "200000.00"}
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "K8": None, "K9": None, "K11": None,
                "H1": h1_data, "I3": i3_data, "G14": None, "F2": None,
            }.get(code)
            checks = await gate.check_k_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "K11勾稽" in c.check_name)
        assert rule.passed is True
        assert "跳过" in rule.details


# ---------------------------------------------------------------------------
# Test boundary conditions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestKCycleBoundaryConditions:
    """Test K 循环三角勾稽边界条件."""

    async def test_vr_k8_01_at_tolerance_boundary(self, db_session, project_id):
        """VR-K8-01 容差边界: 差异 = 0.99 应通过"""
        gate = ConsistencyGate(db_session)
        # expected = 350万；actual = 350万 + 0.99 = 3500000.99
        k8_data = {
            "k8_total": "3500000.99",
            "k8_payroll": "1000000.00",
            "k8_depreciation": "500000.00",
            "k8_other": "2000000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "K8": k8_data, "K9": None, "K11": None,
                "H1": None, "I3": None, "G14": None, "F2": None,
            }.get(code)
            checks = await gate.check_k_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "K8勾稽" in c.check_name)
        assert rule.passed is True

    async def test_vr_k8_01_just_above_tolerance(self, db_session, project_id):
        """VR-K8-01 容差刚超: 差异 = 1.0 应失败（formula: diff < 1.0）"""
        gate = ConsistencyGate(db_session)
        k8_data = {
            "k8_total": "3500001.00",
            "k8_payroll": "1000000.00",
            "k8_depreciation": "500000.00",
            "k8_other": "2000000.00",
        }
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = lambda pid, code: {
                "K8": k8_data, "K9": None, "K11": None,
                "H1": None, "I3": None, "G14": None, "F2": None,
            }.get(code)
            checks = await gate.check_k_cycle_triangle_reconciliation(project_id, 2025)

        rule = next(c for c in checks if "K8勾稽" in c.check_name)
        assert rule.passed is False

    async def test_skip_does_not_block_overall(self, db_session, project_id):
        """所有 K 规则 skip 时 ConsistencyResult 应仍为 pass"""
        gate = ConsistencyGate(db_session)
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock, return_value=None
        ):
            checks = await gate.check_k_cycle_triangle_reconciliation(project_id, 2025)

        # 3 条规则全部 skip 但 passed=True
        assert len(checks) == 3
        for c in checks:
            assert c.passed is True
        # 模拟 ConsistencyResult 不会被 K 阻断
        result = ConsistencyResult(overall="pass", checks=checks)
        assert result.has_blocking_failures is False


# ---------------------------------------------------------------------------
# Integration: run_all_checks includes K cycle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestKCycleIntegration:
    """Verify K cycle checks are included in run_all_checks."""

    async def test_run_all_checks_includes_k_cycle(self, db_session, project_id):
        """run_all_checks 包含 K 循环 3 条 VR 检查"""
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
        ):
            result = await gate.run_all_checks(project_id, 2025)

        # K cycle produces 3 checks (all skip since _get_wp_parsed_data returns None)
        k_checks = [c for c in result.checks if "K" in c.check_name and "勾稽" in c.check_name]
        assert len(k_checks) == 3
        # All should be passed=True (skip mode)
        assert all(c.passed for c in k_checks)
        # Verify rule names cover K8/K9/K11
        joined = " ".join(c.check_name for c in k_checks)
        assert "K8勾稽" in joined
        assert "K9勾稽" in joined
        assert "K11勾稽" in joined

    async def test_run_all_checks_does_not_break_other_cycles(
        self, db_session, project_id
    ):
        """K 循环加入后 J 循环回归无影响 — 验证 J 测试套件的核心断言模式"""
        gate = ConsistencyGate(db_session)
        with patch.object(
            gate, "_get_wp_parsed_data", new_callable=AsyncMock, return_value=None
        ):
            result = await gate.run_all_checks(project_id, 2025)

        # 应包含 J 循环 3 条 + K 循环 3 条 = 共 6 条 cycle 三角勾稽
        cycle_checks = [
            c for c in result.checks
            if "勾稽" in c.check_name and (
                "J1" in c.check_name or "K8" in c.check_name
                or "K9" in c.check_name or "K11" in c.check_name
            )
        ]
        assert len(cycle_checks) >= 6
