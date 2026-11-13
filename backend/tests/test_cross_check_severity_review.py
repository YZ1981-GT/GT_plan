"""S2 任务4（ADR-CCN-05）：表间审核严重度（缺省 warning = 只提示）与报表审核汇总。

- 规则定义：缺省 / 认不出的 severity 按 warning 处理；合法值 blocking 保留（不被门禁消费）。
- 执行结果：内置 7 条与用户规则的 outcome / issue 都带 severity，缺省 warning。
- 接口：`/formula/report-cross-check` 的 results / issue_list 逐条带 severity。
- 报表审核汇总：warning 级未通过计入「提示」，不计入「失败」（consistent 不因此变 False）；
  blocking 级未通过仍判不一致；缺省严重度按 blocking（fail-closed，与旧口径一致）。
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.routers import reports as reports_router
from app.routers.formula_logic_check import _serialize
from app.services.formula_management.engine import IssueItem
from app.services.formula_management.logic_check import (
    BUILTIN_CROSS_CHECK_SEVERITY,
    CrossCheckOutcome,
    CrossCheckResult,
    build_cross_check_formulas,
)
from app.services.formula_settings.cross_check_rules import (
    DEFAULT_SEVERITY,
    RULE_FIELDS,
    _definition,
    severity_of,
)
from app.services.report_audit_checks import split_by_severity


class TestRuleSeverityDefault:
    def test_severity_is_a_stored_rule_field(self):
        assert "severity" in RULE_FIELDS

    def test_missing_severity_defaults_to_warning_and_is_not_stored(self):
        definition = _definition({"label": "x", "left_ref": "ROW('a')", "right_ref": "ROW('b')"})
        assert "severity" not in definition
        assert severity_of(definition.get("severity")) == "warning"

    def test_unknown_severity_falls_back_to_warning_and_is_not_stored(self):
        assert "severity" not in _definition({"severity": "fatal"})
        assert DEFAULT_SEVERITY == "warning"
        assert severity_of(None) == "warning"

    def test_default_severity_keeps_legacy_definition_equal(self):
        """旧定义（无 severity 键）与缺省定义逐字段相等 ⇒ 原样保存不会分叉成项目层覆盖。"""
        legacy = {"label": "x", "left_ref": "ROW('a')", "operator": "=", "right_ref": "ROW('b')",
                  "description": "", "tolerance": "0.01"}
        assert _definition({**legacy, "severity": "warning"}) == _definition(legacy)

    def test_blocking_is_kept_as_a_value_but_not_forced(self):
        assert _definition({"severity": "blocking"})["severity"] == "blocking"

    def test_builtin_seven_checks_default_to_warning(self):
        assert BUILTIN_CROSS_CHECK_SEVERITY == "warning"
        assert len(build_cross_check_formulas()) == 7


class TestResultSeverityDefault:
    def test_outcome_and_issue_default_to_warning(self):
        assert CrossCheckOutcome(formula_id="f", description="d", expression="e", passed=False).severity == "warning"
        assert IssueItem(formula_id="f", addr_id=None, description="d").severity == "warning"

    def test_serialized_response_carries_severity(self):
        issue = IssueItem(formula_id="XR-1", addr_id=None, description="差额", severity="warning")
        outcome = CrossCheckOutcome(formula_id="XR-1", description="差额", expression="a = b", passed=False,
                                    severity="warning")
        payload = _serialize(CrossCheckResult(issues=[issue], outcomes=[outcome]))
        assert payload["issue_list"][0]["severity"] == "warning"
        assert payload["results"][0]["severity"] == "warning"
        assert payload["results"][0]["passed"] is False


class TestSplitBySeverity:
    def test_warning_failure_is_a_hint_not_a_failure(self):
        checks = [{"name": "资产=负债+权益", "passed": False, "severity": "warning"}]
        failures, hints = split_by_severity(checks)
        assert failures == []
        assert [c["name"] for c in hints] == ["资产=负债+权益"]

    def test_blocking_failure_is_a_failure(self):
        checks = [{"name": "试算不平", "passed": False, "severity": "blocking"}]
        failures, hints = split_by_severity(checks)
        assert [c["name"] for c in failures] == ["试算不平"]
        assert hints == []

    def test_missing_severity_is_fail_closed_as_failure(self):
        failures, hints = split_by_severity([{"name": "旧项", "passed": False}])
        assert len(failures) == 1 and hints == []

    def test_passed_items_are_counted_on_neither_side(self):
        failures, hints = split_by_severity([{"name": "ok", "passed": True, "severity": "blocking"}])
        assert failures == [] and hints == []


@pytest.mark.asyncio
class TestReportReviewSummary:
    """报表审核汇总端点（reports.consistency_check）：提示不让结论变「不一致」。"""

    async def _call(self, checks: list[dict]):
        pid = uuid.uuid4()
        with patch("app.services.report_audit_checks.run_report_audit", AsyncMock(return_value=checks)), \
                patch.object(reports_router, "_resolve_applicable_standard", AsyncMock(return_value="soe")):
            return await reports_router.consistency_check(pid, 2025, db=None, current_user=None)

    @staticmethod
    def _item(name: str, passed: bool, **extra) -> dict:
        return {"name": name, "category": "logic_check", "category_label": "🔍 逻辑审核", "passed": passed,
                "expected": "0", "actual": "1", "diff": "1", "formula": None, "source": "t", **extra}

    async def test_warning_only_failures_keep_report_consistent(self):
        out = await self._call([
            self._item("平衡", True, severity="blocking"),
            self._item("提示项", False, severity="warning"),
        ])
        assert out["consistent"] is True
        assert (out["failed_count"], out["hint_count"]) == (0, 1)

    async def test_blocking_failure_makes_report_inconsistent(self):
        out = await self._call([
            self._item("提示项", False, severity="warning"),
            self._item("试算不平", False, severity="blocking"),
        ])
        assert out["consistent"] is False
        assert (out["failed_count"], out["hint_count"]) == (1, 1)

    async def test_each_check_row_exposes_severity(self):
        out = await self._call([self._item("平衡", True)])
        assert out["checks"][0]["severity"] == "blocking"
        assert out["no_result"] is False

    async def test_no_checks_is_no_result_not_consistent(self):
        out = await self._call([])
        assert out["consistent"] is None
        assert out["no_result"] is True
        assert (out["failed_count"], out["hint_count"]) == (0, 0)
