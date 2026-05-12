"""F16 / Sprint 11.8: /metrics 端点集成测试

背景：
- FastAPI `GET /metrics` 返回 Prometheus 格式文本（`CONTENT_TYPE_LATEST`）
- 包含 5 个核心指标：
    ledger_import_duration_seconds (histogram)
    ledger_import_jobs_total       (counter)
    ledger_dataset_count           (gauge)
    event_outbox_dlq_depth         (gauge)
    ledger_import_health_status    (gauge)
- prometheus_client 未安装时降级为 `# prometheus_client not installed\n`

本测试覆盖：
1. GET /metrics 返回 200
2. 响应体含 3 个核心 metric 名称（duration/jobs_total/dataset_count）
3. 推送一个 phase duration observation 后重新 GET，新数据点出现
4. inc_job_status + set_dataset_count 等埋点函数可执行不抛错
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def metrics_client():
    """启动一个不跑 lifespan 的 FastAPI 实例直接访问 /metrics。

    绕过 main.py 的 lifespan（迁移 / 事件注册 / worker 启动）对测试的干扰。
    只挂载 /metrics 端点本身。
    """
    from fastapi import FastAPI, Response

    app = FastAPI()

    @app.get("/metrics")
    async def _metrics():
        from app.services.ledger_import.metrics import render_metrics

        body, content_type = render_metrics()
        return Response(content=body, media_type=content_type)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _prom_available() -> bool:
    """prometheus_client 是否可用（CI 默认装，本地环境可能缺）。"""
    try:
        import prometheus_client  # noqa: F401
    except ImportError:
        return False
    return True


# ---------------------------------------------------------------------------
# Case 1: /metrics 返回 200 + 正确 content-type
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_200(metrics_client: AsyncClient):
    resp = await metrics_client.get("/metrics")
    assert resp.status_code == 200
    body = resp.text
    assert body  # 非空

    if _prom_available():
        # Prometheus 官方 content-type
        assert (
            "text/plain" in resp.headers.get("content-type", "")
            or "application/openmetrics-text" in resp.headers.get("content-type", "")
        )
    else:
        assert "prometheus_client not installed" in body


# ---------------------------------------------------------------------------
# Case 2: 响应体包含 3 个核心 metric 名称
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_metrics_endpoint_contains_core_metrics(metrics_client: AsyncClient):
    if not _prom_available():
        pytest.skip("prometheus_client 未安装，metric 名称检查跳过")

    from app.services.ledger_import.metrics import (
        inc_job_status,
        observe_phase_duration,
        set_dataset_count,
    )

    # 写入一些数据点确保 metric 在输出中（否则未记录的 counter 不会出现）
    observe_phase_duration("detect", 1.2)
    inc_job_status("completed")
    set_dataset_count("proj-test", "active", 2)

    resp = await metrics_client.get("/metrics")
    body = resp.text

    assert "ledger_import_duration_seconds" in body
    assert "ledger_import_jobs_total" in body
    assert "ledger_dataset_count" in body


# ---------------------------------------------------------------------------
# Case 3: 推送 metric 值后新数据点可见（phase duration）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_observe_phase_duration_appears_in_metrics(metrics_client: AsyncClient):
    if not _prom_available():
        pytest.skip("prometheus_client 未安装")

    from app.services.ledger_import.metrics import observe_phase_duration

    marker_phase = "test_phase_11_8_" + "unique"
    observe_phase_duration(marker_phase, 42.0)

    resp = await metrics_client.get("/metrics")
    assert resp.status_code == 200
    body = resp.text
    # histogram 样本带 label — phase="test_phase_11_8_unique"
    assert marker_phase in body


# ---------------------------------------------------------------------------
# Case 4: set_dlq_depth / set_health_status 等埋点函数不抛异常
# ---------------------------------------------------------------------------


def test_metric_functions_are_safe_without_prometheus():
    """即使 prometheus_client 未安装，埋点函数也不应抛异常（_Stub 降级）。"""
    from app.services.ledger_import.metrics import (
        inc_job_status,
        observe_phase_duration,
        set_dataset_count,
        set_dlq_depth,
        set_health_status,
    )

    # 所有这些都应无异常
    observe_phase_duration("x", 0.0)
    inc_job_status("queued")
    set_dataset_count("p1", "active", 1)
    set_dlq_depth(5)
    set_health_status(0)


# ---------------------------------------------------------------------------
# Case 5: render_metrics 返回 (bytes, str)
# ---------------------------------------------------------------------------


def test_render_metrics_returns_bytes_and_content_type():
    from app.services.ledger_import.metrics import render_metrics

    body, content_type = render_metrics()
    assert isinstance(body, bytes)
    assert isinstance(content_type, str)
    assert len(body) > 0
    assert len(content_type) > 0
