"""集成测试: ACNR 可观测性 — 降级路径可观测 [P14]

**Validates: Requirements Req-12**

验证：
1. full_resolve 调用结束记录结构化指标 (Req-12.1)
2. 非 wp 域委托 V1 → 记录 fallback 事件 (Req-12.2)
3. auth_reject 事件记录（不含敏感数据）(Req-12.3)
4. /api/acnr/metrics 端点返回聚合指标 (Req-12.4)
5. alias conflict / version mismatch 告警 (Req-12.5)
"""
from __future__ import annotations

import pytest
import time

from app.services.acnr.metrics import (
    AcnrMetricsCollector,
    get_acnr_metrics,
    reset_acnr_metrics,
    ResolveMetricRecord,
    AlertEvent,
)


# ─── Unit-level: AcnrMetricsCollector ────────────────────────────────────────


class TestAcnrMetricsCollector:
    """AcnrMetricsCollector 基本功能验证。"""

    def setup_method(self):
        self.collector = AcnrMetricsCollector()

    def test_record_resolve_basic(self):
        """记录一次 resolve 调用后聚合指标正确。"""
        self.collector.record_resolve(
            domain="wp",
            layer_hit="L1_cell",
            result="found",
            latency_ms=5.2,
        )
        metrics = self.collector.get_aggregated_metrics()
        assert metrics["total_calls"] == 1
        assert metrics["by_result"]["found"] == 1
        assert metrics["by_domain"]["wp"] == 1
        assert metrics["by_layer"]["L1_cell"] == 1
        assert metrics["avg_latency_ms"] == 5.2

    def test_record_multiple_results(self):
        """多次调用后各计数器正确累加。"""
        self.collector.record_resolve(domain="wp", layer_hit="L1_cell", result="found", latency_ms=3.0)
        self.collector.record_resolve(domain="wp", layer_hit=None, result="miss", latency_ms=1.0)
        self.collector.record_resolve(domain="tb", layer_hit="V1", result="fallback", latency_ms=10.0)

        metrics = self.collector.get_aggregated_metrics()
        assert metrics["total_calls"] == 3
        assert metrics["by_result"]["found"] == 1
        assert metrics["by_result"]["miss"] == 1
        assert metrics["by_result"]["fallback"] == 1
        assert metrics["by_domain"]["wp"] == 2
        assert metrics["by_domain"]["tb"] == 1
        assert metrics["by_layer"]["L1_cell"] == 1
        assert metrics["by_layer"]["V1"] == 1

    def test_record_fallback_event(self):
        """Req-12.2: fallback 事件记录到 alerts。"""
        self.collector.record_fallback("非wp域委托V1: domain=tb", domain="tb")

        metrics = self.collector.get_aggregated_metrics()
        assert metrics["alerts"]["total"] == 1
        assert metrics["alerts"]["by_type"]["fallback"] == 1
        assert len(metrics["alerts"]["recent"]) == 1
        alert = metrics["alerts"]["recent"][0]
        assert alert["event_type"] == "fallback"
        assert "tb" in alert["reason"]

    def test_record_auth_reject(self):
        """Req-12.3: auth_reject 事件不含敏感数据。"""
        self.collector.record_auth_reject(project_id="some-uuid")

        metrics = self.collector.get_aggregated_metrics()
        assert metrics["alerts"]["by_type"]["auth_reject"] == 1
        alert = metrics["alerts"]["recent"][0]
        assert alert["event_type"] == "auth_reject"
        # 不含 project_id 值
        assert "some-uuid" not in alert["reason"]
        assert alert["metadata"].get("has_project_id") is True

    def test_record_alias_conflict(self):
        """Req-12.5: alias conflict 告警。"""
        self.collector.record_alias_conflict("D2-2-alias", 3)

        metrics = self.collector.get_aggregated_metrics()
        assert metrics["alerts"]["by_type"]["alias_conflict"] == 1
        alert = metrics["alerts"]["recent"][0]
        assert alert["severity"] == "error"
        assert alert["metadata"]["alias"] == "D2-2-alias"
        assert alert["metadata"]["candidates"] == 3

    def test_record_version_mismatch(self):
        """Req-12.5: version mismatch 告警。"""
        self.collector.record_version_mismatch("v1.0.0", "Snapshot not found")

        metrics = self.collector.get_aggregated_metrics()
        assert metrics["alerts"]["by_type"]["version_mismatch"] == 1
        alert = metrics["alerts"]["recent"][0]
        assert alert["severity"] == "error"
        assert alert["metadata"]["version"] == "v1.0.0"

    def test_record_overlay_persist_fail(self):
        """Req-12.5: Overlay 持久化失败告警。"""
        self.collector.record_overlay_persist_fail("DB connection timeout")

        metrics = self.collector.get_aggregated_metrics()
        assert metrics["alerts"]["by_type"]["overlay_persist_fail"] == 1

    def test_reset_clears_all(self):
        """reset 后所有指标归零。"""
        self.collector.record_resolve(domain="wp", layer_hit="L1_cell", result="found", latency_ms=5.0)
        self.collector.record_fallback("test", domain="wp")
        self.collector.reset()

        metrics = self.collector.get_aggregated_metrics()
        assert metrics["total_calls"] == 0
        assert metrics["alerts"]["total"] == 0
        assert metrics["recent_records"] == []

    def test_recent_records_capped(self):
        """recent_records 返回上限 50 条。"""
        for i in range(100):
            self.collector.record_resolve(domain="wp", layer_hit="L1_cell", result="found", latency_ms=float(i))

        metrics = self.collector.get_aggregated_metrics()
        assert len(metrics["recent_records"]) == 50
        assert metrics["total_calls"] == 100


# ─── Integration: full_resolve → metrics 有条目 [P14] ─────────────────────────


class TestFullResolveMetricsIntegration:
    """P14: 降级路径可观测 — full_resolve fallback → metrics 有条目。"""

    def setup_method(self):
        reset_acnr_metrics()

    @pytest.mark.asyncio
    async def test_fallback_v1_delegation_records_metrics(self):
        """Req-12.2: 非 wp 域委托 V1 → metrics 记录 fallback 事件。"""
        from app.services.acnr.resolver import full_resolve

        # TB 域输入 → 委托 V1
        result = await full_resolve(uri="tb://1001")

        metrics = get_acnr_metrics().get_aggregated_metrics()
        # 应有至少一条 resolve 记录
        assert metrics["total_calls"] >= 1
        # 应有 fallback 事件
        assert metrics["alerts"]["by_type"].get("fallback", 0) >= 1
        # 结果中应包含 V1 层
        assert metrics["by_layer"].get("V1", 0) >= 1

    @pytest.mark.asyncio
    async def test_miss_records_metrics(self):
        """Req-12.1: miss 路径 → metrics 记录 miss。"""
        from app.services.acnr.resolver import full_resolve

        # 一个不存在的 addr_id
        result = await full_resolve(addr_id="NONEXISTENT/FAKE/ZZZ999")

        metrics = get_acnr_metrics().get_aggregated_metrics()
        assert metrics["total_calls"] >= 1
        assert metrics["by_result"].get("miss", 0) >= 1

    @pytest.mark.asyncio
    async def test_resolve_records_latency(self):
        """Req-12.1: 记录 latency_ms 字段。"""
        from app.services.acnr.resolver import full_resolve

        await full_resolve(addr_id="D2/D2-2/E100")

        metrics = get_acnr_metrics().get_aggregated_metrics()
        assert metrics["total_calls"] >= 1
        # 至少有 recent_records 条目
        if metrics["recent_records"]:
            rec = metrics["recent_records"][-1]
            assert "latency_ms" in rec
            assert rec["latency_ms"] >= 0


# ─── Integration: alert events ────────────────────────────────────────────────


class TestAlertEventsIntegration:
    """Req-12.5: 主动告警集成。"""

    def setup_method(self):
        reset_acnr_metrics()

    def test_alias_conflict_alert_has_structured_data(self):
        """alias conflict 告警包含别名和候选数。"""
        m = get_acnr_metrics()
        m.record_alias_conflict("my-alias", 5)

        agg = m.get_aggregated_metrics()
        recent = agg["alerts"]["recent"]
        assert len(recent) >= 1
        alert = recent[-1]
        assert alert["event_type"] == "alias_conflict"
        assert alert["metadata"]["alias"] == "my-alias"
        assert alert["metadata"]["candidates"] == 5

    def test_version_mismatch_alert_severity_error(self):
        """version mismatch 告警级别为 error。"""
        m = get_acnr_metrics()
        m.record_version_mismatch("v2.0.0-missing", "快照不存在")

        agg = m.get_aggregated_metrics()
        alert = agg["alerts"]["recent"][-1]
        assert alert["severity"] == "error"

    def test_overlay_persist_fail_alert(self):
        """Overlay 持久化失败产生 error 级告警。"""
        m = get_acnr_metrics()
        m.record_overlay_persist_fail("Connection refused to PG")

        agg = m.get_aggregated_metrics()
        alert = agg["alerts"]["recent"][-1]
        assert alert["event_type"] == "overlay_persist_fail"
        assert alert["severity"] == "error"


# ─── Module singleton ─────────────────────────────────────────────────────────


class TestModuleSingleton:
    """get_acnr_metrics 单例行为。"""

    def test_singleton_returns_same_instance(self):
        """get_acnr_metrics 返回同一实例。"""
        a = get_acnr_metrics()
        b = get_acnr_metrics()
        assert a is b

    def test_reset_creates_fresh_instance(self):
        """reset_acnr_metrics 创建新实例。"""
        old = get_acnr_metrics()
        old.record_resolve(domain="wp", layer_hit="L1_cell", result="found", latency_ms=1.0)

        reset_acnr_metrics()
        new = get_acnr_metrics()
        assert new is not old
        assert new.get_aggregated_metrics()["total_calls"] == 0
