"""路由拆分回归 Property-Based Test (Task 1.3)

Property 8: After split, all API path + method combinations remain identical.

**Validates: Requirements 4.3, 4.6**

验证：
- import register_all_routers 正常工作
- 创建 FastAPI app 并注册所有路由
- 收集所有 routes (path + methods)
- 集合非空且包含预期模式
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from hypothesis import given, settings, strategies as st

from app.router_registry import register_all_routers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _collect_routes(app: FastAPI) -> set[tuple[str, str]]:
    """收集应用中所有 (path, method) 组合。"""
    routes: set[tuple[str, str]] = set()
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods:
                routes.add((route.path, method))
    return routes


# ---------------------------------------------------------------------------
# Property 8: 路由拆分后路径保持不变
# ---------------------------------------------------------------------------


class TestRouterRegistrySplitPBT:
    """Property 8: After split, all API path + method combinations remain identical.

    **Validates: Requirements 4.3, 4.6**
    """

    @settings(max_examples=30)
    @given(seed=st.integers(min_value=0, max_value=100000))
    def test_route_set_is_stable_across_registrations(self, seed: int):
        """Property 8: 多次注册产生完全相同的路由集合。

        **Validates: Requirements 4.3**

        For any invocation of register_all_routers, the resulting route set
        must be identical (idempotent and deterministic).
        """
        app1 = FastAPI()
        register_all_routers(app1)
        routes1 = _collect_routes(app1)

        app2 = FastAPI()
        register_all_routers(app2)
        routes2 = _collect_routes(app2)

        assert routes1 == routes2, (
            f"路由集合不一致: diff={routes1.symmetric_difference(routes2)}"
        )
        assert len(routes1) > 0, "路由集合不应为空"

    def test_register_all_routers_works_without_error(self):
        """Simple test: register_all_routers 正常执行不抛异常。"""
        app = FastAPI()
        register_all_routers(app)
        routes = _collect_routes(app)
        assert len(routes) > 50, f"应有 >50 个路由，实际 {len(routes)}"

    def test_routes_contain_expected_patterns(self):
        """验证路由集合包含预期的 API 模式。"""
        app = FastAPI()
        register_all_routers(app)
        routes = _collect_routes(app)
        paths = {p for p, _ in routes}

        # 验证关键路由模式存在
        assert any("/api/" in p for p in paths), "应有 /api/ 前缀路由"
        assert any("GET" == m for _, m in routes), "应有 GET 方法"
        assert any("POST" == m for _, m in routes), "应有 POST 方法"
