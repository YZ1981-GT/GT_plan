# Feature: zero-downtime-deployment, Property 2
"""Property 2：每个响应携带版本头。

Validates: Requirements 1.2
任意 HTTP 响应（成功和错误）均携带 X-App-Version 头，
且头值等于当前实例的 get_build_version()["git_commit"]。
"""

import httpx
import pytest
from hypothesis import given, settings, HealthCheck, strategies as st

from app.core.build_version import get_build_version
from app.main import app


@pytest.fixture(autouse=True)
def clear_version_cache():
    get_build_version.cache_clear()
    yield
    get_build_version.cache_clear()


# 样本端点策略：包含成功和错误路径
SAMPLE_ENDPOINTS = [
    "/api/version",
    "/api/health",
    "/livez",
    "/readyz",
    "/api/nonexistent-endpoint-404",
]

endpoint_st = st.sampled_from(SAMPLE_ENDPOINTS)


@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
@given(endpoint=endpoint_st)
@pytest.mark.asyncio
async def test_every_response_has_version_header(endpoint):
    """每个 HTTP 响应（成功和错误）都携带 X-App-Version 头且值等于 git_commit。"""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.get(endpoint)
        # 断言响应携带 X-App-Version 头
        assert "X-App-Version" in resp.headers, (
            f"响应缺少 X-App-Version 头: endpoint={endpoint}, status={resp.status_code}"
        )
        # 断言头值等于当前实例的 git_commit
        expected_commit = get_build_version()["git_commit"]
        assert resp.headers["X-App-Version"] == expected_commit, (
            f"X-App-Version 头值不匹配: got={resp.headers['X-App-Version']!r}, "
            f"expected={expected_commit!r}, endpoint={endpoint}"
        )
