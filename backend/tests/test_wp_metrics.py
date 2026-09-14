"""底稿性能指标收集器单元测试

Task 7.3: 建立 render/save 指标并优化重复调用
Requirements: 8.1-8.3
"""

from __future__ import annotations

import pytest

from app.services.wp_metrics import WpMetricsCollector, wp_metrics


@pytest.fixture(autouse=True)
def reset_global_metrics():
    """每个测试前后重置全局 metrics。"""
    wp_metrics.reset()
    yield
    wp_metrics.reset()


class TestWpMetricsCollector:
    """WpMetricsCollector 单元测试。"""

    def test_initial_state_empty(self):
        m = WpMetricsCollector()
        summary = m.get_summary()
        assert summary["render_config"] == {}
        assert summary["renderer_invocations"] == {}
        assert summary["save"]["conflicts_total"] == 0
        assert summary["save"]["failures_total"] == 0

    def test_observe_render_config_cold_hot(self):
        m = WpMetricsCollector()
        m.observe_render_config("j1-employee-compensation", 7000.0, cold=True)
        m.observe_render_config("j1-employee-compensation", 20.0, cold=False)
        m.observe_render_config("j1-employee-compensation", 25.0, cold=False)

        stats = m.get_render_config_stats()
        assert "j1-employee-compensation|cold" in stats
        assert "j1-employee-compensation|hot" in stats
        cold_stats = stats["j1-employee-compensation|cold"]
        assert cold_stats["count"] == 1
        assert cold_stats["avg"] == 7000.0
        hot_stats = stats["j1-employee-compensation|hot"]
        assert hot_stats["count"] == 2
        assert hot_stats["avg"] == 22.5

    def test_inc_renderer_invocation(self):
        m = WpMetricsCollector()
        m.inc_renderer_invocation("d2-accounts-receivable")
        m.inc_renderer_invocation("d2-accounts-receivable")
        m.inc_renderer_invocation("j1-employee-compensation")

        invocations = m.get_renderer_invocations()
        assert invocations["d2-accounts-receivable"] == 2
        assert invocations["j1-employee-compensation"] == 1

    def test_observe_save_success(self):
        m = WpMetricsCollector()
        m.observe_save(50.0, status="success")
        m.observe_save(80.0, status="success")

        stats = m.get_save_stats()
        assert stats["by_status"]["success"]["count"] == 2
        assert stats["by_status"]["success"]["avg"] == 65.0
        assert stats["conflicts_total"] == 0
        assert stats["failures_total"] == 0

    def test_observe_save_conflict(self):
        m = WpMetricsCollector()
        m.observe_save(100.0, status="conflict")
        m.observe_save(200.0, status="conflict")

        stats = m.get_save_stats()
        assert stats["conflicts_total"] == 2
        assert stats["by_status"]["conflict"]["count"] == 2

    def test_observe_save_error(self):
        m = WpMetricsCollector()
        m.observe_save(500.0, status="error")

        stats = m.get_save_stats()
        assert stats["failures_total"] == 1
        assert stats["by_status"]["error"]["count"] == 1

    def test_time_render_config_context_manager(self):
        m = WpMetricsCollector()
        with m.time_render_config("test-ct", cold=False):
            pass  # 快速操作

        stats = m.get_render_config_stats()
        assert "test-ct|hot" in stats
        assert stats["test-ct|hot"]["count"] == 1
        # 耗时应极小但 > 0
        assert stats["test-ct|hot"]["avg"] >= 0

    def test_time_save_context_manager(self):
        m = WpMetricsCollector()
        with m.time_save() as ctx:
            ctx["status"] = "success"

        stats = m.get_save_stats()
        assert stats["by_status"]["success"]["count"] == 1

    def test_time_save_error_status(self):
        m = WpMetricsCollector()
        with m.time_save() as ctx:
            ctx["status"] = "error"

        stats = m.get_save_stats()
        assert stats["failures_total"] == 1

    def test_reset(self):
        m = WpMetricsCollector()
        m.observe_render_config("x", 100, cold=True)
        m.inc_renderer_invocation("x")
        m.observe_save(50, status="success")
        m.observe_save(50, status="conflict")

        m.reset()
        summary = m.get_summary()
        assert summary["render_config"] == {}
        assert summary["renderer_invocations"] == {}
        assert summary["save"]["conflicts_total"] == 0

    def test_histogram_window_limit(self):
        """直方图保留最近 500 个观测值。"""
        m = WpMetricsCollector()
        for i in range(600):
            m.observe_render_config("x", float(i), cold=False)

        stats = m.get_render_config_stats()
        assert stats["x|hot"]["count"] == 500

    def test_global_singleton(self):
        """全局单例 wp_metrics 可用。"""
        wp_metrics.observe_render_config("g", 10.0, cold=False)
        assert wp_metrics.get_render_config_stats()["g|hot"]["count"] == 1
