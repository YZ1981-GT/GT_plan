"""Tests for Evidence Governance observability + audit retention — Task 7.4 (Wave 6).

Validates: Requirements R12, R13, R15, R16
Properties (partial):
  P25 — 审计事件覆盖（脱敏，不含凭据/原文；告警关联 command-root/transition/trace）
  P27 — 保留期边界（保留期/hold 内禁止修改删除）
  P30 — 质量指标可复算（相同事件序列 → 相同聚合）

覆盖 design §9.3 低基数指标域 + 立即告警（AI coverage gap / manifest hash failure /
跨 scope denied 峰值）+ R12.4 审计保留判定。纯进程内 / 纯函数，无 PG 依赖。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.evidence_governance.audit_retention import (
    DEFAULT_RETENTION_DAYS,
    RetentionStatus,
    assert_audit_mutable,
    evaluate_retention,
    is_within_retention,
)
from app.services.evidence_governance.frozen_contracts import (
    EvidenceErrorCode,
    EvidenceGovernanceError,
)
from app.services.evidence_governance.observability import (
    ALERT_ERROR,
    ALERT_TYPES,
    ALERT_WARNING,
    METRIC_DOMAINS,
    METRIC_OUTCOMES,
    AlertEvent,
    EvidenceGovernanceMetrics,
    get_evidence_metrics,
    reset_evidence_metrics,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. 低基数指标域覆盖（design §9.3）
# ─────────────────────────────────────────────────────────────────────────────

#: design §9.3 明确要求覆盖的域（低基数指标）。
_REQUIRED_DOMAINS = {
    "upload", "boundary", "ref", "ocr_queue", "ocr_failure", "ai_coverage",
    "citation", "stale_age", "stale_closure", "review_reopen", "formal_gate",
    "archive_hash", "hold", "outbox_lag", "pg_pool_wait", "backpressure",
}


class TestMetricDomainCoverage:
    def test_all_design_domains_present(self):
        """§9.3 要求的每个域都在 METRIC_DOMAINS。"""
        missing = _REQUIRED_DOMAINS - set(METRIC_DOMAINS)
        assert missing == set(), f"缺失覆盖域: {missing}"

    def test_alert_types_include_immediate_alerts(self):
        """三类立即告警类型均已声明。"""
        for t in ("ai_coverage_gap", "manifest_hash_failure", "cross_scope_denied_spike"):
            assert t in ALERT_TYPES


# ─────────────────────────────────────────────────────────────────────────────
# 2. 低基数：未知标签收敛 + 计数聚合
# ─────────────────────────────────────────────────────────────────────────────


class TestLowCardinality:
    def test_unknown_domain_coerced_to_other(self):
        m = EvidenceGovernanceMetrics()
        m.record_event(domain="not-a-real-domain-xyz", outcome="accepted")
        agg = m.get_aggregated_metrics()
        assert "other" in agg["counters"]
        assert "not-a-real-domain-xyz" not in agg["counters"]

    def test_unknown_outcome_coerced_to_other(self):
        m = EvidenceGovernanceMetrics()
        m.record_event(domain="upload", outcome="wild-unknown-outcome")
        agg = m.get_aggregated_metrics()
        assert agg["counters"]["upload"] == {"other": 1}

    def test_counter_aggregation(self):
        m = EvidenceGovernanceMetrics()
        m.record_event(domain="upload", outcome="accepted")
        m.record_event(domain="upload", outcome="accepted", count=2)
        m.record_event(domain="upload", outcome="rejected")
        agg = m.get_aggregated_metrics()
        assert agg["counters"]["upload"] == {"accepted": 3, "rejected": 1}

    @given(
        events=st.lists(
            st.tuples(
                st.sampled_from(sorted(METRIC_DOMAINS)),
                st.sampled_from(sorted(METRIC_OUTCOMES)),
            ),
            max_size=40,
        )
    )
    def test_series_cardinality_bounded(self, events):
        """series 数恒 <= |domain| × |outcome|（低基数，不因输入量爆炸）。"""
        m = EvidenceGovernanceMetrics()
        for d, o in events:
            m.record_event(domain=d, outcome=o)
        agg = m.get_aggregated_metrics()
        total_series = sum(len(v) for v in agg["counters"].values())
        assert total_series <= len(METRIC_DOMAINS) * len(METRIC_OUTCOMES)


# ─────────────────────────────────────────────────────────────────────────────
# 3. gauge 分桶 + 可复算（P30 语义）
# ─────────────────────────────────────────────────────────────────────────────


class TestGaugeRecomputable:
    def test_gauge_snapshot_fields(self):
        m = EvidenceGovernanceMetrics()
        for v in (2.0, 4.0, 90.0):
            m.observe_gauge(domain="stale_age", value=v)
        snap = m.get_aggregated_metrics()["gauges"]["stale_age"]
        assert snap["count"] == 3
        assert snap["max"] == 90.0
        assert snap["sum"] == 96.0
        assert snap["avg"] == 32.0

    @given(values=st.lists(st.floats(min_value=0, max_value=100000, allow_nan=False, allow_infinity=False), max_size=30))
    def test_gauge_deterministic_recompute(self, values):
        """相同观测序列 → 完全相同的 gauge 聚合（P30 可复算）。"""
        m1 = EvidenceGovernanceMetrics()
        m2 = EvidenceGovernanceMetrics()
        for v in values:
            m1.observe_gauge(domain="outbox_lag", value=v)
            m2.observe_gauge(domain="outbox_lag", value=v)
        assert (
            m1.get_aggregated_metrics()["gauges"]
            == m2.get_aggregated_metrics()["gauges"]
        )


# ─────────────────────────────────────────────────────────────────────────────
# 4. 告警脱敏（P25：不含凭据/原文/绝对路径/prompt-answer）
# ─────────────────────────────────────────────────────────────────────────────


class TestAlertRedaction:
    def test_alert_metadata_redacted(self):
        m = EvidenceGovernanceMetrics()
        ev = m.record_alert(
            alert_type="gate_bypass",
            reason="test",
            severity=ALERT_WARNING,
            metadata={
                "password": "hunter2",
                "token": "abc",
                "file_path": "/etc/secret",
                "raw_text": "附件原文机密内容",
                "prompt": "完整 prompt",
                "answer": "完整 answer",
                "safe_id": "keep-me",
            },
        )
        md = ev.metadata
        assert md["password"] == "[redacted]"
        assert md["token"] == "[redacted]"
        assert md["file_path"] == "[redacted]"
        assert md["raw_text"] == "[redacted]"
        assert md["prompt"] == "[redacted]"
        assert md["answer"] == "[redacted]"
        assert md["safe_id"] == "keep-me"

    def test_alert_correlates_command_root_and_trace(self):
        m = EvidenceGovernanceMetrics()
        root = str(uuid.uuid4())
        trans = str(uuid.uuid4())
        ev = m.record_alert(
            alert_type="gate_bypass",
            reason="x",
            command_root_id=root,
            transition_id=trans,
            trace_id="trace-123",
        )
        assert ev.command_root_id == root
        assert ev.transition_id == trans
        assert ev.trace_id == "trace-123"

    def test_unknown_alert_type_coerced(self):
        m = EvidenceGovernanceMetrics()
        ev = m.record_alert(alert_type="totally-unknown", reason="x")
        assert ev.alert_type in ALERT_TYPES


# ─────────────────────────────────────────────────────────────────────────────
# 5. 立即告警：AI coverage gap / manifest hash failure / 跨 scope denied 峰值
# ─────────────────────────────────────────────────────────────────────────────


class TestImmediateAlerts:
    def test_ai_coverage_gap_alerts_only_when_positive(self):
        m = EvidenceGovernanceMetrics()
        assert m.alert_ai_coverage_gap(gap_count=0) is None
        ev = m.alert_ai_coverage_gap(gap_count=3)
        assert ev is not None
        assert ev.alert_type == "ai_coverage_gap"
        assert ev.severity == ALERT_ERROR
        # gap 计数进入 ai_coverage 域
        agg = m.get_aggregated_metrics()
        assert agg["counters"]["ai_coverage"]["gap"] == 3

    def test_manifest_hash_failure_alerts_immediately(self):
        m = EvidenceGovernanceMetrics()
        ev = m.alert_manifest_hash_failure(command_root_id=str(uuid.uuid4()))
        assert ev.alert_type == "manifest_hash_failure"
        assert ev.severity == ALERT_ERROR
        assert m.get_aggregated_metrics()["counters"]["archive_hash"]["mismatch"] == 1

    def test_cross_scope_denied_spike(self):
        m = EvidenceGovernanceMetrics(
            cross_scope_window_seconds=60.0, cross_scope_threshold=3
        )
        t0 = 1000.0
        assert m.record_cross_scope_denied(now=t0) is None
        assert m.record_cross_scope_denied(now=t0 + 1) is None
        ev = m.record_cross_scope_denied(now=t0 + 2)
        assert ev is not None
        assert ev.alert_type == "cross_scope_denied_spike"
        assert ev.severity == ALERT_ERROR

    def test_cross_scope_window_expiry_no_spike(self):
        """窗口外的事件被剔除，不误触发峰值。"""
        m = EvidenceGovernanceMetrics(
            cross_scope_window_seconds=10.0, cross_scope_threshold=3
        )
        assert m.record_cross_scope_denied(now=0.0) is None
        assert m.record_cross_scope_denied(now=100.0) is None  # 旧事件已过期
        assert m.record_cross_scope_denied(now=200.0) is None  # 仍不足阈值

    def test_threshold_alert_only_above_threshold(self):
        m = EvidenceGovernanceMetrics()
        assert m.record_threshold_alert(
            alert_type="ocr_failure_rate", observed=0.05, threshold=0.1
        ) is None
        ev = m.record_threshold_alert(
            alert_type="ocr_failure_rate", observed=0.2, threshold=0.1
        )
        assert ev is not None
        assert ev.alert_type == "ocr_failure_rate"


# ─────────────────────────────────────────────────────────────────────────────
# 6. 单例 + reset
# ─────────────────────────────────────────────────────────────────────────────


class TestSingleton:
    def test_singleton_stable(self):
        assert get_evidence_metrics() is get_evidence_metrics()

    def test_reset_clears(self):
        m = get_evidence_metrics()
        m.record_event(domain="upload", outcome="accepted")
        reset_evidence_metrics()
        agg = get_evidence_metrics().get_aggregated_metrics()
        assert agg["counters"] == {}
        assert agg["alerts"]["total"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 7. 审计保留判定（R12.4；P27 部分）
# ─────────────────────────────────────────────────────────────────────────────

_NOW = datetime(2025, 1, 1, tzinfo=timezone.utc)


class TestAuditRetention:
    def test_none_archived_within_retention(self):
        assert is_within_retention(archived_at=None, now=_NOW) is True

    def test_permanent_retention(self):
        old = _NOW - timedelta(days=100000)
        assert is_within_retention(archived_at=old, retention_days=0, now=_NOW) is True

    def test_before_expiry_within(self):
        archived = _NOW - timedelta(days=10)
        assert is_within_retention(archived_at=archived, retention_days=30, now=_NOW) is True

    def test_after_expiry_not_within(self):
        archived = _NOW - timedelta(days=40)
        assert is_within_retention(archived_at=archived, retention_days=30, now=_NOW) is False

    def test_naive_archived_at_treated_as_utc(self):
        archived = datetime(2024, 12, 22)  # naive, 10 天前
        assert is_within_retention(archived_at=archived, retention_days=30, now=_NOW) is True

    def test_default_retention_days_long(self):
        assert DEFAULT_RETENTION_DAYS >= 3650

    def test_evaluate_and_forbid_under_hold(self):
        status = evaluate_retention(
            archived_at=_NOW - timedelta(days=99999), under_legal_hold=True, now=_NOW
        )
        assert status.mutation_forbidden is True
        with pytest.raises(EvidenceGovernanceError) as exc:
            assert_audit_mutable(status)
        assert exc.value.error_code == EvidenceErrorCode.LEGAL_HOLD_ACTIVE

    def test_forbid_within_retention_no_hold(self):
        status = evaluate_retention(
            archived_at=_NOW - timedelta(days=1),
            under_legal_hold=False,
            retention_days=30,
            now=_NOW,
        )
        assert status.mutation_forbidden is True
        with pytest.raises(EvidenceGovernanceError) as exc:
            assert_audit_mutable(status)
        assert exc.value.error_code == EvidenceErrorCode.VERSION_CONFLICT

    def test_mutable_when_expired_and_no_hold(self):
        status = evaluate_retention(
            archived_at=_NOW - timedelta(days=40),
            under_legal_hold=False,
            retention_days=30,
            now=_NOW,
        )
        assert status.mutation_forbidden is False
        assert status.retention_expired is True
        assert_audit_mutable(status)  # 不抛异常

    @given(
        days_ago=st.integers(min_value=0, max_value=20000),
        retention=st.integers(min_value=1, max_value=10000),
        hold=st.booleans(),
    )
    def test_property_forbid_iff_hold_or_within(self, days_ago, retention, hold):
        """mutation_forbidden ⟺ (under_legal_hold OR within_retention)（R12.4）。"""
        archived = _NOW - timedelta(days=days_ago)
        status = evaluate_retention(
            archived_at=archived, under_legal_hold=hold, retention_days=retention, now=_NOW
        )
        within = days_ago < retention
        assert status.within_retention == within
        assert status.mutation_forbidden == (hold or within)
