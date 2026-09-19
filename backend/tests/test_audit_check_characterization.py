"""审计检查复核收口面板加固 — 零回归 characterization 基线（Task 1.1）

锁定 `audit-check-review-gate-hardening` spec 改造前的**当前实际行为**，作为后续
（M0-M3 聚合器/summary/新鲜度/签认等）改造的零回归安全网。

覆盖四个既有真源（Requirements 10.2/10.3/10.4 零回归红线）：

1. legacy `parsed_data.fine_checks`/`fine_summary` 读取路径
   —— `GET /api/projects/{pid}/fine-checks/summary`（`get_fine_checks_summary`）
   直接读缓存的组织行为：无 fine_checks 的底稿不跳过（返回 checks=[]/summary={}）、
   按 str(wp_id) 组织、每项含 wp_code/wp_name/audit_cycle。
2. QC-27（`FineCheckBlockingRule`）：`fine_checks` 中 `severity=blocking` 且
   `passed=false` 产生 blocking finding。
3. QC-28（`FineCheckWarningRule`）：`severity=warning` 且未通过产生 warning。
4. `_run_audit_checks` 对各 check_type（balance/cross_ref/movement/completeness/
   aging/reconciliation/confirmation/check|analysis|cutoff）的判定与 pending(None)
   语义 —— 尤其锁定 `_check_aging`/`_check_reconciliation`/`_check_confirmation` 返回
   None（待验证）、`_check_sheet_filled` >50% 判 True 的弱判定。

**这是 characterization 测试**：断言当前实际行为（哪怕"不理想"，如大量 None / 弱判定），
目的是后续改造若破坏这些行为能被测出。不"修正"当前行为。

纯 example-based（无 hypothesis / 无 DB）；QC-27/28 复用既有 QCContext mock 模式
（参见 test_qc_blocking_rules.py），check 不触 db；summary 端点用 mock db 会话。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


# ═══════════════════════════════════════════════════════════════════
# Section 1 — legacy fine_checks/fine_summary 读取路径：summary 端点
# ═══════════════════════════════════════════════════════════════════


def _make_summary_db(rows: list[tuple]):
    """构造 mock AsyncSession，`db.execute(...)` 的 .all() 返回给定 rows。

    每 row 为 5-tuple: (wp_id, parsed_data, wp_code, wp_name, audit_cycle)
    —— 对齐 `get_fine_checks_summary` 内部解包顺序。
    """
    db = AsyncMock()
    result = MagicMock()
    result.all.return_value = rows
    db.execute.return_value = result
    return db


class TestFineChecksSummaryEndpoint:
    """锁定 `get_fine_checks_summary` 直接读缓存的组织行为。"""

    @pytest.mark.asyncio
    async def test_workpaper_without_fine_checks_not_skipped(self):
        """无 fine_checks 的底稿**仍出现在结果中**，checks=[]/summary={}（不隐藏、不跳过）。"""
        from app.routers.wp_fine_rules import get_fine_checks_summary

        wp_id = uuid4()
        rows = [(wp_id, {}, "E1", "货币资金", "E")]  # parsed_data 为空 dict
        db = _make_summary_db(rows)

        result = await get_fine_checks_summary(project_id=str(uuid4()), db=db, _user=None)

        assert str(wp_id) in result
        entry = result[str(wp_id)]
        assert entry["checks"] == []
        assert entry["summary"] == {}

    @pytest.mark.asyncio
    async def test_parsed_data_none_defaults_empty(self):
        """parsed_data 为 None 时 checks=[]/summary={}（`pd = parsed_data or {}`）。"""
        from app.routers.wp_fine_rules import get_fine_checks_summary

        wp_id = uuid4()
        rows = [(wp_id, None, "D2", "应收账款", "D")]
        db = _make_summary_db(rows)

        result = await get_fine_checks_summary(project_id=str(uuid4()), db=db, _user=None)

        assert result[str(wp_id)]["checks"] == []
        assert result[str(wp_id)]["summary"] == {}

    @pytest.mark.asyncio
    async def test_cached_checks_passthrough_and_shape(self):
        """有缓存的底稿原样透传 checks/summary，且每项含 wp_code/wp_name/audit_cycle，key=str(wp_id)。"""
        from app.routers.wp_fine_rules import get_fine_checks_summary

        wp_id = uuid4()
        checks = [{"code": "E1-CHK-01", "passed": True, "severity": "blocking"}]
        summary = {"closing_audited": 1000}
        pd = {"fine_checks": checks, "fine_summary": summary}
        rows = [(wp_id, pd, "E1", "货币资金", "E")]
        db = _make_summary_db(rows)

        result = await get_fine_checks_summary(project_id=str(uuid4()), db=db, _user=None)

        entry = result[str(wp_id)]
        assert entry["wp_id"] == str(wp_id)
        assert entry["wp_code"] == "E1"
        assert entry["wp_name"] == "货币资金"
        assert entry["audit_cycle"] == "E"
        assert entry["checks"] == checks
        assert entry["summary"] == summary

    @pytest.mark.asyncio
    async def test_multiple_workpapers_keyed_by_wp_id(self):
        """多底稿：结果字典按 str(wp_id) 组织，每底稿一条。"""
        from app.routers.wp_fine_rules import get_fine_checks_summary

        wp1, wp2 = uuid4(), uuid4()
        rows = [
            (wp1, {"fine_checks": [{"code": "A"}]}, "E1", "货币资金", "E"),
            (wp2, {}, "D2", "应收账款", "D"),
        ]
        db = _make_summary_db(rows)

        result = await get_fine_checks_summary(project_id=str(uuid4()), db=db, _user=None)

        assert set(result.keys()) == {str(wp1), str(wp2)}
        assert result[str(wp1)]["checks"] == [{"code": "A"}]
        assert result[str(wp2)]["checks"] == []

    @pytest.mark.asyncio
    async def test_empty_project_returns_empty_dict(self):
        """项目无底稿时返回空 dict。"""
        from app.routers.wp_fine_rules import get_fine_checks_summary

        db = _make_summary_db([])
        result = await get_fine_checks_summary(project_id=str(uuid4()), db=db, _user=None)
        assert result == {}


# ═══════════════════════════════════════════════════════════════════
# Section 2 & 3 — QC-27 / QC-28 fine_check 门禁联动
# ═══════════════════════════════════════════════════════════════════


def _qc_context(fine_checks):
    """构造 QCContext（parsed_data.fine_checks = 给定列表）；QC-27/28 check 不触 db。"""
    from app.services.qc_engine import QCContext

    wp = MagicMock()
    wp.id = uuid4()
    wp.project_id = uuid4()
    wp.parsed_data = {"fine_checks": fine_checks} if fine_checks is not None else {}
    return QCContext(db=AsyncMock(), working_paper=wp, project_id=wp.project_id)


class TestQc27FineCheckBlocking:
    """QC-27 `FineCheckBlockingRule`：blocking 级未通过 → 阻断 finding。"""

    @pytest.mark.asyncio
    async def test_no_fine_checks_returns_empty(self):
        from app.services.qc_engine import FineCheckBlockingRule

        findings = await FineCheckBlockingRule().check(_qc_context([]))
        assert findings == []

    @pytest.mark.asyncio
    async def test_no_fine_checks_key_returns_empty(self):
        from app.services.qc_engine import FineCheckBlockingRule

        findings = await FineCheckBlockingRule().check(_qc_context(None))
        assert findings == []

    @pytest.mark.asyncio
    async def test_blocking_failed_produces_finding(self):
        from app.services.qc_engine import FineCheckBlockingRule

        checks = [{"code": "E1-CHK-01", "severity": "blocking", "passed": False,
                   "description": "审定表↔试算表差异"}]
        findings = await FineCheckBlockingRule().check(_qc_context(checks))
        assert len(findings) == 1
        assert findings[0].rule_id == "QC-27"
        assert findings[0].severity == "blocking"
        assert "E1-CHK-01" in findings[0].message

    @pytest.mark.asyncio
    async def test_blocking_passed_no_finding(self):
        from app.services.qc_engine import FineCheckBlockingRule

        checks = [{"code": "E1-CHK-01", "severity": "blocking", "passed": True}]
        findings = await FineCheckBlockingRule().check(_qc_context(checks))
        assert findings == []

    @pytest.mark.asyncio
    async def test_warning_failed_ignored_by_qc27(self):
        """QC-27 只管 blocking，warning 级未通过不产 finding。"""
        from app.services.qc_engine import FineCheckBlockingRule

        checks = [{"code": "E1-CHK-05", "severity": "warning", "passed": False}]
        findings = await FineCheckBlockingRule().check(_qc_context(checks))
        assert findings == []

    @pytest.mark.asyncio
    async def test_passed_missing_defaults_true_no_finding(self):
        """passed 缺省时 `chk.get('passed', True)` 视为 True → 不产 finding（当前弱行为）。"""
        from app.services.qc_engine import FineCheckBlockingRule

        checks = [{"code": "E1-CHK-01", "severity": "blocking"}]  # 无 passed 键
        findings = await FineCheckBlockingRule().check(_qc_context(checks))
        assert findings == []

    @pytest.mark.asyncio
    async def test_pending_none_treated_as_not_passed_produces_finding(self):
        """passed=None（pending/待验证）当前被 `not None`=True 判为未通过 → 产 blocking finding。

        锁定当前实际行为：pending 项在 QC-27 里被当作"未通过"阻断（非"跳过"）。
        """
        from app.services.qc_engine import FineCheckBlockingRule

        checks = [{"code": "E1-CHK-12", "severity": "blocking", "passed": None}]
        findings = await FineCheckBlockingRule().check(_qc_context(checks))
        assert len(findings) == 1
        assert findings[0].rule_id == "QC-27"


class TestQc28FineCheckWarning:
    """QC-28 `FineCheckWarningRule`：warning 级未通过 → 警告 finding。"""

    @pytest.mark.asyncio
    async def test_no_fine_checks_returns_empty(self):
        from app.services.qc_engine import FineCheckWarningRule

        findings = await FineCheckWarningRule().check(_qc_context([]))
        assert findings == []

    @pytest.mark.asyncio
    async def test_warning_failed_produces_finding(self):
        from app.services.qc_engine import FineCheckWarningRule

        checks = [{"code": "E1-CHK-05", "severity": "warning", "passed": False,
                   "description": "分析程序波动"}]
        findings = await FineCheckWarningRule().check(_qc_context(checks))
        assert len(findings) == 1
        assert findings[0].rule_id == "QC-28"
        assert findings[0].severity == "warning"
        assert "E1-CHK-05" in findings[0].message

    @pytest.mark.asyncio
    async def test_warning_passed_no_finding(self):
        from app.services.qc_engine import FineCheckWarningRule

        checks = [{"code": "E1-CHK-05", "severity": "warning", "passed": True}]
        findings = await FineCheckWarningRule().check(_qc_context(checks))
        assert findings == []

    @pytest.mark.asyncio
    async def test_blocking_failed_ignored_by_qc28(self):
        """QC-28 只管 warning，blocking 级未通过不产 finding。"""
        from app.services.qc_engine import FineCheckWarningRule

        checks = [{"code": "E1-CHK-01", "severity": "blocking", "passed": False}]
        findings = await FineCheckWarningRule().check(_qc_context(checks))
        assert findings == []

    @pytest.mark.asyncio
    async def test_mixed_checks_each_rule_picks_own_severity(self):
        """混合检查：QC-27 只取 blocking-failed，QC-28 只取 warning-failed。"""
        from app.services.qc_engine import FineCheckBlockingRule, FineCheckWarningRule

        checks = [
            {"code": "B1", "severity": "blocking", "passed": False},
            {"code": "W1", "severity": "warning", "passed": False},
            {"code": "B2", "severity": "blocking", "passed": True},
            {"code": "W2", "severity": "warning", "passed": True},
        ]
        blocking = await FineCheckBlockingRule().check(_qc_context(checks))
        warning = await FineCheckWarningRule().check(_qc_context(checks))
        assert [f.rule_id for f in blocking] == ["QC-27"]
        assert "B1" in blocking[0].message
        assert [f.rule_id for f in warning] == ["QC-28"]
        assert "W1" in warning[0].message


# ═══════════════════════════════════════════════════════════════════
# Section 4 — _run_audit_checks 各 check_type 判定 + pending(None) 语义
# ═══════════════════════════════════════════════════════════════════


def _run(check, *, wp_code="X", summary_rows=None, sheets_extra=None):
    """驱动 `_run_audit_checks`，返回单个检查的结果 dict。

    check: {id/code, type, severity, description}
    summary_rows: 注入到 sheets["{wp_code}-1"].rows
    sheets_extra: 额外 sheet（如明细表 {wp_code}-2）
    """
    from app.services.wp_fine_rule_checks import _run_audit_checks

    rule = {"wp_code": wp_code, "audit_checks": [check]}
    sheets = {f"{wp_code}-1": {"found": True, "rows": summary_rows or {}}}
    if sheets_extra:
        sheets.update(sheets_extra)
    summary = {}
    results = _run_audit_checks(rule, sheets, summary)
    assert len(results) == 1
    return results[0]


class TestRunAuditChecksBalance:
    """balance 类型判定。"""

    def test_chk01_passed(self):
        r = _run(
            {"id": "X-CHK-01", "type": "balance", "severity": "blocking"},
            summary_rows={"total": {"closing_audited": 1000.0},
                          "tb_balance": {"closing_audited": 1000.0}},
        )
        assert r["passed"] is True
        assert r["diff"] == 0.0

    def test_chk01_failed_with_diff(self):
        r = _run(
            {"id": "X-CHK-01", "type": "balance", "severity": "blocking"},
            summary_rows={"total": {"closing_audited": 1000.0},
                          "tb_balance": {"closing_audited": 900.0}},
        )
        assert r["passed"] is False
        assert r["diff"] == 100.0
        assert "差异" in r["message"]

    def test_chk01_incomplete_data_pending(self):
        """total 有值但 tb 缺失 → None（数据不完整）。"""
        r = _run(
            {"id": "X-CHK-01", "type": "balance", "severity": "blocking"},
            summary_rows={"total": {"closing_audited": 1000.0}},
        )
        assert r["passed"] is None
        assert "数据不完整" in r["message"]

    def test_chk02_always_pending(self):
        """CHK-02（vs 报表）恒 None（待外部报表数据验证）。"""
        r = _run(
            {"id": "X-CHK-02", "type": "balance", "severity": "blocking"},
            summary_rows={"total": {"closing_audited": 1000.0}},
        )
        assert r["passed"] is None
        assert "报表" in r["message"]


class TestRunAuditChecksCrossRef:
    """cross_ref 类型判定（CHK-03 现金审定 vs 现金明细合计）。"""

    def test_chk03_passed(self):
        r = _run(
            {"id": "X-CHK-03", "type": "cross_ref", "severity": "warning"},
            summary_rows={"cash": {"closing_audited": 300.0}},
            sheets_extra={"X-2": {"found": True, "detail_rows": [
                {"closing_audited": 100.0}, {"closing_audited": 200.0}]}},
        )
        assert r["passed"] is True
        assert r["diff"] == 0.0

    def test_chk03_no_detail_data_pending(self):
        """现金明细无数据 → None。"""
        r = _run(
            {"id": "X-CHK-03", "type": "cross_ref", "severity": "warning"},
            summary_rows={"cash": {"closing_audited": 300.0}},
        )
        assert r["passed"] is None
        assert "无数据" in r["message"]


class TestRunAuditChecksMovement:
    """movement 类型：期初+变动=期末。"""

    def test_movement_passed(self):
        r = _run(
            {"id": "X-CHK-M", "type": "movement", "severity": "warning"},
            summary_rows={"cash": {"opening_audited": 100.0, "change_amount": 10.0,
                                   "closing_audited": 110.0}},
        )
        assert r["passed"] is True

    def test_movement_failed(self):
        r = _run(
            {"id": "X-CHK-M", "type": "movement", "severity": "warning"},
            summary_rows={"cash": {"opening_audited": 100.0, "change_amount": 10.0,
                                   "closing_audited": 200.0}},
        )
        assert r["passed"] is False
        assert "变动不一致" in r["message"]


class TestRunAuditChecksCompleteness:
    """completeness 类型：明细表有数据 → True，否则 None。"""

    def test_completeness_with_detail_true(self):
        r = _run(
            {"id": "X-CHK-C", "type": "completeness", "severity": "warning"},
            sheets_extra={"X-2": {"found": True, "detail_rows": [{"a": 1}]}},
        )
        assert r["passed"] is True

    def test_completeness_no_detail_pending(self):
        """无明细行 → None（弱判定：已找到 sheet 但无明细）。"""
        r = _run({"id": "X-CHK-C", "type": "completeness", "severity": "warning"})
        assert r["passed"] is None


class TestRunAuditChecksPendingByDesign:
    """锁定"设计上恒返回 None"的检查类型（当前实现的弱判定/待验证）。"""

    @pytest.mark.parametrize("code", ["X-CHK-12", "X-CHK-13", "X-CHK-14"])
    def test_aging_always_pending(self, code):
        """_check_aging：CHK-12/13/14 全返 None（需明细账龄/政策/上年数据）。"""
        r = _run({"id": code, "type": "aging", "severity": "warning"})
        assert r["passed"] is None

    def test_reconciliation_pending_when_not_found(self):
        """_check_reconciliation：未找到调节表 → None。"""
        r = _run({"id": "X-CHK-R", "type": "reconciliation", "severity": "warning"})
        assert r["passed"] is None
        assert "调节表" in r["message"]

    def test_confirmation_pending_when_not_found(self):
        """_check_confirmation：未找到函证结果汇总 → None。"""
        r = _run({"id": "X-CHK-F", "type": "confirmation", "severity": "warning"})
        assert r["passed"] is None


class TestRunAuditChecksSheetFilledWeakVerdict:
    """check/analysis/cutoff → _check_sheet_filled 的 >50% 弱判定。"""

    def test_over_50_percent_true(self):
        """已找到 sheet 全部有数据（100% > 50%）→ True（弱判定：填了就算通过）。"""
        r = _run(
            {"id": "X-CHK-8", "type": "check", "severity": "warning"},
            summary_rows={"cash": {"closing_audited": 100.0}},  # X-1 found + 有数据
            sheets_extra={"X-2": {"found": True, "detail_rows": [{"a": 1}]}},
        )
        assert r["passed"] is True
        assert "%" in r["message"]

    def test_at_or_below_50_percent_pending(self):
        """已找到 sheet 均无数据（0% ≤ 50%）→ None。"""
        r = _run(
            {"id": "X-CHK-8", "type": "analysis", "severity": "warning"},
            summary_rows={},  # X-1 found 但 rows 空 → 无数据
            sheets_extra={"X-2": {"found": True, "detail_rows": []}},
        )
        assert r["passed"] is None

    def test_no_sheet_found_pending(self):
        """无任何 found sheet → None。"""
        from app.services.wp_fine_rule_checks import _run_audit_checks

        rule = {"wp_code": "X", "audit_checks": [
            {"id": "X-CHK-8", "type": "cutoff", "severity": "warning"}]}
        sheets = {"X-1": {"found": False}}
        results = _run_audit_checks(rule, sheets, {})
        assert results[0]["passed"] is None


class TestRunAuditChecksUnknownAndShape:
    """未知类型 + 结果字段结构。"""

    def test_unknown_type_pending_with_message(self):
        r = _run({"id": "X-CHK-Z", "type": "mystery", "severity": "info"})
        assert r["passed"] is None
        assert "未知检查类型" in r["message"]

    def test_result_item_shape(self):
        """每个检查结果含固定字段集（供前端统一渲染）。"""
        r = _run(
            {"id": "X-CHK-01", "type": "balance", "severity": "blocking",
             "description": "审定↔试算表"},
            summary_rows={"total": {"closing_audited": 1.0},
                          "tb_balance": {"closing_audited": 1.0}},
        )
        assert set(r.keys()) == {
            "code", "type", "severity", "description",
            "passed", "actual", "expected", "diff", "message",
        }
        assert r["code"] == "X-CHK-01"
        assert r["type"] == "balance"
        assert r["severity"] == "blocking"
        assert r["description"] == "审定↔试算表"

    def test_code_falls_back_to_code_key(self):
        """检查项 id 缺失时用 code 键（`check.get('id', check.get('code',''))`）。"""
        from app.services.wp_fine_rule_checks import _run_audit_checks

        rule = {"wp_code": "X", "audit_checks": [
            {"code": "X-CHK-01", "type": "balance", "severity": "blocking"}]}
        sheets = {"X-1": {"found": True, "rows": {
            "total": {"closing_audited": 1.0}, "tb_balance": {"closing_audited": 1.0}}}}
        results = _run_audit_checks(rule, sheets, {})
        assert results[0]["code"] == "X-CHK-01"

    def test_empty_audit_checks_returns_empty(self):
        from app.services.wp_fine_rule_checks import _run_audit_checks

        results = _run_audit_checks({"wp_code": "X", "audit_checks": []}, {}, {})
        assert results == []
