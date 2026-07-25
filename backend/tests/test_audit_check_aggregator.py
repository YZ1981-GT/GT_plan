"""AuditCheckAggregator.recompute_workpaper 单测（Task 2.2）

验证 S1 归并 / S2 结构化转换 / S6 保留 / 去重优先级 / 只写 audit_checks·audit_checks_at
不动 legacy / fail-open（某来源抛异常其余仍产出）。

用 mock wp/idx（MagicMock，parsed_data 用真 dict）+ mock db（AsyncMock，flush no-op），
并 mock 掉 aggregator 模块内绑定的 build_cycle_reconciliation_findings /
build_d2_reconciliation_findings（不触库）。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.audit_check import (
    AuditCheckAggregator,
    AuditCheckSource,
)
from app.services.audit_check.aggregator import _dedup_key, _merge_dedup
from app.services.audit_check.models import AuditCheckItem


# ═══════════════════════════════════════════
# 测试夹具
# ═══════════════════════════════════════════

def _make_wp(parsed_data: dict, wp_id: str = "wp-1"):
    wp = MagicMock()
    wp.id = wp_id
    wp.parsed_data = parsed_data
    return wp


def _make_idx(wp_code: str):
    idx = MagicMock()
    idx.wp_code = wp_code
    return idx


def _make_db():
    db = MagicMock()
    db.flush = AsyncMock(return_value=None)
    return db


def _cycle_finding(code, passed, *, severity="blocking", check_type="balance",
                   actual=100.0, expected=100.0, diff=0.0, message="m"):
    return {
        "code": code,
        "passed": passed,
        "actual": actual,
        "expected": expected,
        "diff": diff,
        "message": message,
        "severity": severity,
        "check_type": check_type,
    }


# ═══════════════════════════════════════════
# S1 fine_rule 归并
# ═══════════════════════════════════════════

async def test_s1_merges_fine_checks_with_source(monkeypatch):
    """S1：fine_checks 逐项补 source=fine_rule + wp_code + produced_at。"""
    monkeypatch.setattr(
        "app.services.audit_check.aggregator.build_cycle_reconciliation_findings",
        AsyncMock(return_value=[]),
    )
    pd = {
        "fine_checks": [
            {"code": "E1-CHK-05", "type": "aging", "passed": True,
             "severity": "warning", "message": "ok"},
        ],
        "fine_extracted_at": "2026-07-20T00:00:00",
    }
    wp = _make_wp(pd)
    idx = _make_idx("E1")
    db = _make_db()

    items = await AuditCheckAggregator().recompute_workpaper(db, wp, idx, year=2025)

    s1 = [it for it in items if it.source == AuditCheckSource.FINE_RULE.value]
    assert len(s1) == 1
    assert s1[0].code == "E1-CHK-05"
    assert s1[0].wp_code == "E1"
    assert s1[0].wp_id == "wp-1"
    assert s1[0].produced_at == "2026-07-20T00:00:00"
    assert s1[0].check_type == "aging"  # legacy type → check_type
    db.flush.assert_awaited_once()


# ═══════════════════════════════════════════
# S2 cycle_recon 结构化转换
# ═══════════════════════════════════════════

async def test_s2_cycle_findings_to_items(monkeypatch):
    """S2：K/N 循环 build_cycle_reconciliation_findings 转 AuditCheckItem。"""
    monkeypatch.setattr(
        "app.services.audit_check.aggregator.build_cycle_reconciliation_findings",
        AsyncMock(return_value=[
            _cycle_finding("K9-RECON-TB", False, diff=10.0, message="不一致"),
            _cycle_finding("K9-RECON-ADJ", None, severity="info",
                           check_type="analysis", message="调整净额"),
        ]),
    )
    wp = _make_wp({})
    idx = _make_idx("K9-1")
    db = _make_db()

    items = await AuditCheckAggregator().recompute_workpaper(db, wp, idx, year=2025)

    s2 = [it for it in items if it.source == AuditCheckSource.CYCLE_RECON.value]
    assert len(s2) == 2
    tb = next(it for it in s2 if it.code == "K9-RECON-TB")
    assert tb.passed is False
    assert tb.diff == 10.0
    assert tb.severity == "blocking"
    assert tb.check_type == "balance"
    assert tb.wp_code == "K9-1"
    assert tb.sheet_hint == "K9-1"  # 审定表 sheet 定位（{cycle}-1）
    # 未覆盖 info 项 passed=None
    adj = next(it for it in s2 if it.code == "K9-RECON-ADJ")
    assert adj.passed is None


async def test_s2_d2_dispatch(monkeypatch):
    """S2：D2 走 build_d2_reconciliation_findings 分支。"""
    d2_mock = AsyncMock(return_value=[_cycle_finding("D2-RECON-TB", True)])
    cycle_mock = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "app.services.audit_check.aggregator.build_d2_reconciliation_findings", d2_mock)
    monkeypatch.setattr(
        "app.services.audit_check.aggregator.build_cycle_reconciliation_findings",
        cycle_mock)
    wp = _make_wp({})
    idx = _make_idx("D2")
    db = _make_db()

    items = await AuditCheckAggregator().recompute_workpaper(db, wp, idx, year=2025)

    d2_mock.assert_awaited_once_with("wp-1")
    cycle_mock.assert_not_awaited()
    assert any(it.code == "D2-RECON-TB" for it in items)


# ═══════════════════════════════════════════
# 去重优先级（cycle_recon > fine_rule）
# ═══════════════════════════════════════════

async def test_dedup_cycle_recon_supersedes_fine_rule_tb(monkeypatch):
    """去重：cycle_recon 审定↔TB 命中时丢弃 fine_rule 的 CHK-01 balance 项。"""
    monkeypatch.setattr(
        "app.services.audit_check.aggregator.build_cycle_reconciliation_findings",
        AsyncMock(return_value=[_cycle_finding("K9-RECON-TB", False, diff=5.0)]),
    )
    pd = {
        "fine_checks": [
            {"code": "K9-CHK-01", "type": "balance", "passed": True,
             "severity": "blocking", "message": "审定↔试算表"},
            {"code": "K9-CHK-05", "type": "aging", "passed": True,
             "severity": "warning", "message": "其他检查"},
        ],
        "fine_extracted_at": "2026-07-20T00:00:00",
    }
    wp = _make_wp(pd)
    idx = _make_idx("K9-1")
    db = _make_db()

    items = await AuditCheckAggregator().recompute_workpaper(db, wp, idx, year=2025)

    codes = {it.code for it in items}
    # fine_rule 的 CHK-01（审定↔TB）被 cycle_recon 覆盖丢弃
    assert "K9-CHK-01" not in codes
    # cycle_recon TB 项保留
    assert "K9-RECON-TB" in codes
    # 不同勾稽的 fine_rule 项（CHK-05）保留
    assert "K9-CHK-05" in codes


async def test_dedup_keeps_fine_rule_when_no_cycle_counterpart(monkeypatch):
    """去重保守：无同语义 cycle_recon 时保留 fine_rule CHK-01。"""
    monkeypatch.setattr(
        "app.services.audit_check.aggregator.build_cycle_reconciliation_findings",
        AsyncMock(return_value=[]),  # 无 cycle_recon
    )
    pd = {
        "fine_checks": [
            {"code": "K9-CHK-01", "type": "balance", "passed": True,
             "severity": "blocking", "message": "审定↔试算表"},
        ],
    }
    wp = _make_wp(pd)
    idx = _make_idx("K9-1")
    db = _make_db()

    items = await AuditCheckAggregator().recompute_workpaper(db, wp, idx, year=2025)
    assert any(it.code == "K9-CHK-01" for it in items)


def test_dedup_key_conservative_none():
    """_dedup_key：无法明确判定同一勾稽的项返回 None（不去重）。"""
    # cycle_recon 信息项 RECON-ADJ → None
    adj = AuditCheckItem(
        code="K9-RECON-ADJ", source=AuditCheckSource.CYCLE_RECON.value,
        wp_code="K9-1", severity="info", check_type="analysis",
        description="", message="", produced_at="",
    )
    assert _dedup_key(adj) is None
    # fine_rule 非 CHK-01/CHK-03 的项 → None
    other = AuditCheckItem(
        code="K9-CHK-09", source=AuditCheckSource.FINE_RULE.value,
        wp_code="K9-1", severity="warning", check_type="aging",
        description="", message="", produced_at="",
    )
    assert _dedup_key(other) is None
    # S6 上报项 → None（不参与 fine_rule/cycle_recon 去重）
    reported = AuditCheckItem(
        code="X", source=AuditCheckSource.TB_RECON.value,
        wp_code="K9-1", severity="blocking", check_type="balance",
        description="", message="", produced_at="",
    )
    assert _dedup_key(reported) is None


def test_dedup_detail_semantic():
    """_dedup_key：审定↔明细语义（RECON-DETAIL / CHK-03 cross_ref）归一。"""
    cyc = AuditCheckItem(
        code="D2-RECON-DETAIL", source=AuditCheckSource.CYCLE_RECON.value,
        wp_code="D2", severity="warning", check_type="cross_ref",
        description="", message="", produced_at="",
    )
    fr = AuditCheckItem(
        code="D2-CHK-03", source=AuditCheckSource.FINE_RULE.value,
        wp_code="D2", severity="warning", check_type="cross_ref",
        description="", message="", produced_at="",
    )
    assert _dedup_key(cyc) == _dedup_key(fr)
    # _merge_dedup 丢弃 fine_rule 保留 cycle_recon
    merged = _merge_dedup([fr, cyc])
    assert cyc in merged
    assert fr not in merged


# ═══════════════════════════════════════════
# S6 保留（recompute 不清除已上报）
# ═══════════════════════════════════════════

async def test_s6_reported_preserved(monkeypatch):
    """S6：已上报 source（tb_recon 等）在 recompute 时原样保留。"""
    monkeypatch.setattr(
        "app.services.audit_check.aggregator.build_cycle_reconciliation_findings",
        AsyncMock(return_value=[]),
    )
    pd = {
        "fine_checks": [],
        "audit_checks": [
            {"code": "G7-REPORT-01", "source": "report_cross_check",
             "wp_code": "G7", "wp_id": "wp-1", "check_type": "cross_ref",
             "severity": "warning", "passed": False, "message": "报表勾稽",
             "produced_at": "2026-07-24T00:00:00"},
            # 后端自算 source（cycle_recon）不应作为 S6 保留（recompute 会重算）
            {"code": "G7-RECON-TB", "source": "cycle_recon",
             "wp_code": "G7", "check_type": "balance", "severity": "blocking",
             "passed": True, "message": "旧的", "produced_at": "old"},
        ],
    }
    wp = _make_wp(pd)
    idx = _make_idx("G7")  # G7 不在 cycle registry → S2 无输出
    db = _make_db()

    items = await AuditCheckAggregator().recompute_workpaper(db, wp, idx, year=2025)

    codes = {it.code for it in items}
    assert "G7-REPORT-01" in codes  # S6 上报项保留
    assert "G7-RECON-TB" not in codes  # 旧 cycle_recon 缓存项不作 S6 保留


# ═══════════════════════════════════════════
# 只写 audit_checks / audit_checks_at 不动 legacy
# ═══════════════════════════════════════════

async def test_only_writes_audit_checks_keys(monkeypatch):
    """写缓存只改 audit_checks / audit_checks_at，不动 fine_checks 等 legacy 字段。"""
    monkeypatch.setattr(
        "app.services.audit_check.aggregator.build_cycle_reconciliation_findings",
        AsyncMock(return_value=[]),
    )
    pd = {
        "fine_checks": [{"code": "E1-CHK-01", "type": "balance", "passed": True,
                         "severity": "blocking", "message": "x"}],
        "fine_summary": {"closing_audited": 999},
        "fine_extracted_at": "2026-07-20T00:00:00",
        "other_field": "keep-me",
    }
    wp = _make_wp(pd)
    idx = _make_idx("E1")
    db = _make_db()

    await AuditCheckAggregator().recompute_workpaper(db, wp, idx, year=2025)

    # legacy 字段逐字节不变
    assert wp.parsed_data["fine_checks"] == [
        {"code": "E1-CHK-01", "type": "balance", "passed": True,
         "severity": "blocking", "message": "x"}]
    assert wp.parsed_data["fine_summary"] == {"closing_audited": 999}
    assert wp.parsed_data["fine_extracted_at"] == "2026-07-20T00:00:00"
    assert wp.parsed_data["other_field"] == "keep-me"
    # 新字段写入
    assert "audit_checks" in wp.parsed_data
    assert "audit_checks_at" in wp.parsed_data
    assert isinstance(wp.parsed_data["audit_checks"], list)


async def test_empty_parsed_data_still_writes(monkeypatch):
    """parsed_data 为 None 时也能安全写入两个新键。"""
    monkeypatch.setattr(
        "app.services.audit_check.aggregator.build_cycle_reconciliation_findings",
        AsyncMock(return_value=[]),
    )
    wp = _make_wp(None)
    wp.parsed_data = None
    idx = _make_idx("E1")
    db = _make_db()

    await AuditCheckAggregator().recompute_workpaper(db, wp, idx, year=2025)
    assert wp.parsed_data["audit_checks"] == []
    assert "audit_checks_at" in wp.parsed_data


# ═══════════════════════════════════════════
# fail-open：某来源抛异常其余仍产出
# ═══════════════════════════════════════════

async def test_fail_open_s2_exception_keeps_s1(monkeypatch):
    """S2 抛异常时不影响 S1 产出（fail-open）。"""
    monkeypatch.setattr(
        "app.services.audit_check.aggregator.build_cycle_reconciliation_findings",
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    pd = {
        "fine_checks": [{"code": "K9-CHK-05", "type": "aging", "passed": True,
                         "severity": "warning", "message": "ok"}],
        "fine_extracted_at": "2026-07-20T00:00:00",
    }
    wp = _make_wp(pd)
    idx = _make_idx("K9-1")
    db = _make_db()

    items = await AuditCheckAggregator().recompute_workpaper(db, wp, idx, year=2025)
    # S2 异常被隔离，S1 仍产出
    assert any(it.code == "K9-CHK-05" for it in items)
    # 仍写缓存
    assert "audit_checks" in wp.parsed_data


async def test_fail_open_s1_bad_fine_checks(monkeypatch):
    """S1 fine_checks 非法结构不整体崩，S2 仍产出。"""
    monkeypatch.setattr(
        "app.services.audit_check.aggregator.build_cycle_reconciliation_findings",
        AsyncMock(return_value=[_cycle_finding("K9-RECON-TB", True)]),
    )
    pd = {"fine_checks": "not-a-list", "fine_extracted_at": "t"}
    wp = _make_wp(pd)
    idx = _make_idx("K9-1")
    db = _make_db()

    items = await AuditCheckAggregator().recompute_workpaper(db, wp, idx, year=2025)
    # S1 异常（对 str 迭代成字符），S2 正常
    assert any(it.code == "K9-RECON-TB" for it in items)
