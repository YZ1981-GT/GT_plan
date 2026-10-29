"""S2 ADR-CCN-04: XR 进签字判据 — 转换表 + observe/enforce + 磁盘变异

测试矩阵:
- 8 组参数化转换用例（XR 结果 status → GateRuleHit severity/message）
- 2 组端点用例（observe → warning / enforce → blocking）
- 磁盘变异（注释掉 skip→not_executed → 测试红 → sha256 恢复 → 测试绿）
"""

import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.phase14_enums import GateSeverity, CheckStatus
from app.services.gate_engine import GateRuleHit

# ── Fixtures ───────────────────────────────────────────────────


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()
    db.begin_nested = AsyncMock()
    # begin_nested returns a context manager with commit/rollback
    sp = AsyncMock()
    sp.commit = AsyncMock()
    sp.rollback = AsyncMock()
    db.begin_nested.return_value = sp
    return db


@pytest.fixture
def project_id():
    return uuid.uuid4()


# ── 辅助：构造 XR execute 结果 ─────────────────────────────────


def _xr_result(rule_id: str, status: str, *, severity: str = "warning",
               left: float | None = None, right: float | None = None,
               diff: float | None = None, reason: str = "", error: str = "") -> dict:
    details: dict = {}
    if reason:
        details["reason"] = reason
    if error:
        details["error"] = error
    return {
        "rule_id": rule_id,
        "description": f"测试规则 {rule_id}",
        "status": status,
        "left_amount": left,
        "right_amount": right,
        "difference": diff,
        "details": details,
    }


# ── 转换表参数化用例（8 组）──────────────────────────────────


class TestConversionTable:
    """XR 结果 status → CrossCheckPassedRule.check() 的 GateRuleHit"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "xr_results, year, expect_hit, expect_severity_contains, expect_message_contains",
        [
            # 1. 单条 pass → 放行（None）
            pytest.param(
                [_xr_result("XR-01", "pass")],
                2025, False, None, None,
                id="single_pass",
            ),
            # 2. fail + blocking → hit with blocking (enforce) / warning (observe)
            pytest.param(
                [_xr_result("XR-01", "fail", severity="blocking",
                            left=100.0, right=90.0, diff=10.0)],
                2025, True, GateSeverity.warning, "未全部通过",
                id="fail_blocking_observe",
            ),
            # 3. fail + warning → hit with warning
            pytest.param(
                [_xr_result("XR-03", "fail", severity="warning",
                            left=50.0, right=40.0, diff=10.0)],
                2025, True, GateSeverity.warning, "差额",
                id="fail_warning",
            ),
            # 4. skip → not_executed → hit
            pytest.param(
                [_xr_result("XR-05", "skip", reason="数据不足，跳过校验")],
                2025, True, GateSeverity.warning, "未执行",
                id="skip_to_not_executed",
            ),
            # 5. not_executed → hit
            pytest.param(
                [_xr_result("XR-08", "not_executed",
                            reason="利息合理性规则尚未实现")],
                2025, True, GateSeverity.warning, "未执行",
                id="not_executed",
            ),
            # 6. error → hit
            pytest.param(
                [_xr_result("XR-99", "error", error="数据库连接失败")],
                2025, True, GateSeverity.warning, "异常",
                id="error",
            ),
            # 7. year=None → not_executed
            pytest.param(
                [], None, True, GateSeverity.warning, "项目未设置审计年度",
                id="year_none",
            ),
            # 8. 所有结果 pass → 放行
            pytest.param(
                [
                    _xr_result("XR-01", "pass"),
                    _xr_result("XR-02", "pass"),
                    _xr_result("XR-06", "pass"),
                ],
                2025, False, None, None,
                id="all_pass",
            ),
        ],
    )
    async def test_conversion(
        self,
        mock_db,
        project_id,
        xr_results,
        year,
        expect_hit,
        expect_severity_contains,
        expect_message_contains,
    ):
        from app.services.gate_rules_cross_check import CrossCheckPassedRule

        rule = CrossCheckPassedRule()
        context = {"project_id": project_id, "year": year}

        with (
            patch(
                "app.services.project_audit_year.fetch_project_audit_year",
                new=AsyncMock(return_value=year),
            ),
            patch(
                "app.services.wp_cross_check_service.CrossCheckService.execute",
                new=AsyncMock(return_value=xr_results),
            ),
            patch(
                "app.services.wp_cross_check_service.CrossCheckService._persist_results",
                new=AsyncMock(),
            ),
            patch.dict(os.environ, {"CONSISTENCY_GATE_ENFORCEMENT": "observe"}),
        ):
            hit = await rule.check(mock_db, context)

        if not expect_hit:
            assert hit is None, f"期望放行但返回了 hit: {hit}"
        else:
            assert hit is not None, "期望命中但返回了 None"
            assert isinstance(hit, GateRuleHit)
            if expect_severity_contains is not None:
                assert hit.severity == expect_severity_contains, (
                    f"期望 severity={expect_severity_contains}, 实际={hit.severity}"
                )
            if expect_message_contains is not None:
                assert expect_message_contains in hit.message, (
                    f"期望消息含 '{expect_message_contains}', 实际='{hit.message}'"
                )


# ── observe/enforce 端点用例（2 组）──────────────────────────


class TestObserveEnforce:
    """observe 模式下 warning 不阻断，enforce 模式下 blocking 阻断"""

    @pytest.mark.asyncio
    async def test_observe_mode_not_blocking(self, mock_db, project_id):
        """observe 模式：XR skip → warning（不阻断签字）"""
        from app.services.gate_rules_cross_check import CrossCheckPassedRule

        rule = CrossCheckPassedRule()
        xr_results = [
            _xr_result("XR-08", "not_executed", reason="利息合理性规则尚未实现"),
        ]
        context = {"project_id": project_id, "year": 2025}

        with (
            patch(
                "app.services.project_audit_year.fetch_project_audit_year",
                new=AsyncMock(return_value=2025),
            ),
            patch(
                "app.services.wp_cross_check_service.CrossCheckService.execute",
                new=AsyncMock(return_value=xr_results),
            ),
            patch(
                "app.services.wp_cross_check_service.CrossCheckService._persist_results",
                new=AsyncMock(),
            ),
            patch.dict(os.environ, {"CONSISTENCY_GATE_ENFORCEMENT": "observe"}),
        ):
            hit = await rule.check(mock_db, context)

        assert hit is not None
        assert hit.severity == GateSeverity.warning, (
            f"observe 模式下应返回 warning，实际={hit.severity}"
        )

    @pytest.mark.asyncio
    async def test_enforce_mode_blocking(self, mock_db, project_id):
        """enforce 模式：XR not_executed → blocking（阻断签字）"""
        from app.services.gate_rules_cross_check import CrossCheckPassedRule

        rule = CrossCheckPassedRule()
        xr_results = [
            _xr_result("XR-08", "not_executed", reason="利息合理性规则尚未实现"),
        ]
        context = {"project_id": project_id, "year": 2025}

        with (
            patch(
                "app.services.project_audit_year.fetch_project_audit_year",
                new=AsyncMock(return_value=2025),
            ),
            patch(
                "app.services.wp_cross_check_service.CrossCheckService.execute",
                new=AsyncMock(return_value=xr_results),
            ),
            patch(
                "app.services.wp_cross_check_service.CrossCheckService._persist_results",
                new=AsyncMock(),
            ),
            patch.dict(os.environ, {"CONSISTENCY_GATE_ENFORCEMENT": "enforce"}),
        ):
            hit = await rule.check(mock_db, context)

        assert hit is not None
        assert hit.severity == GateSeverity.blocking, (
            f"enforce 模式下应返回 blocking，实际={hit.severity}"
        )


# ── readiness_facade 映射 ──────────────────────────────────


class TestReadinessFacadeMapping:
    """R4-CROSS-CHECK 在两个映射表中均有注册"""

    def test_sign_off_mapping(self):
        from app.services.readiness_facade import _SIGN_OFF_RULE_CATEGORY
        assert "R4-CROSS-CHECK" in _SIGN_OFF_RULE_CATEGORY
        assert _SIGN_OFF_RULE_CATEGORY["R4-CROSS-CHECK"] == "misc"

    def test_export_package_mapping(self):
        from app.services.readiness_facade import _EXPORT_PACKAGE_RULE_CATEGORY
        assert "R4-CROSS-CHECK" in _EXPORT_PACKAGE_RULE_CATEGORY
        assert _EXPORT_PACKAGE_RULE_CATEGORY["R4-CROSS-CHECK"] == "misc"


# ── XR-05 公式修正验证 ────────────────────────────────────────


class TestXR05FormulaFixed:
    """XR-05 的 formula 应使用 SUM_TB 而非 TB_SUM"""

    def test_xr05_uses_sum_tb(self):
        from app.services.wp_cross_check_service import load_rules

        rules = load_rules(force=True)
        xr05 = next((r for r in rules if r["rule_id"] == "XR-05"), None)
        assert xr05 is not None, "XR-05 规则未找到"
        assert "SUM_TB(" in xr05["formula"], (
            f"XR-05 公式应使用 SUM_TB，实际: {xr05['formula']}"
        )
        assert "TB_SUM(" not in xr05["formula"], (
            f"XR-05 公式不应包含 TB_SUM，实际: {xr05['formula']}"
        )


# ── XR-08 返回 not_executed ──────────────────────────────────


class TestXR08NotExecuted:
    """XR-08 _execute_abs_rule 应返回 not_executed（非 skip）"""

    @pytest.mark.asyncio
    async def test_abs_rule_returns_not_executed(self, mock_db):
        from app.services.wp_cross_check_service import CrossCheckService

        svc = CrossCheckService(mock_db)
        rule = {
            "rule_id": "XR-08",
            "description": "利息收支合理性",
            "formula": "ABS(...)",
            "tolerance": 0.03,
            "severity": "warning",
        }
        result = await svc._execute_abs_rule(uuid.uuid4(), 2025, rule)
        assert result["status"] == "not_executed", (
            f"XR-08 应返回 not_executed，实际={result['status']}"
        )
        assert "利息合理性规则尚未实现" in result["details"].get("reason", "")


# ── CrossCheckPassedRule 使用 fetch_project_audit_year ────────


class TestYearSource:
    """CrossCheckPassedRule 使用 fetch_project_audit_year 而非内联 SQL"""

    @pytest.mark.asyncio
    async def test_uses_fetch_project_audit_year(self, mock_db, project_id):
        """验证调用了 fetch_project_audit_year 而非直接查 trial_balance"""
        from app.services.gate_rules_cross_check import CrossCheckPassedRule

        rule = CrossCheckPassedRule()
        mock_fetch = AsyncMock(return_value=2025)

        with (
            patch(
                "app.services.project_audit_year.fetch_project_audit_year",
                new=mock_fetch,
            ),
            patch(
                "app.services.wp_cross_check_service.CrossCheckService.execute",
                new=AsyncMock(return_value=[_xr_result("XR-01", "pass")]),
            ),
            patch(
                "app.services.wp_cross_check_service.CrossCheckService._persist_results",
                new=AsyncMock(),
            ),
        ):
            # context 不带 year，逼迫规则调 fetch_project_audit_year
            context = {"project_id": project_id}
            await rule.check(mock_db, context)

        mock_fetch.assert_awaited_once_with(mock_db, project_id)
