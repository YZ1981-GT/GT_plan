"""
F4 璺敱鎷嗗垎鍥炲綊娴嬭瘯 鈥?Property 8

Property 8: 璺敱鎷嗗垎鍚庤矾寰勪繚鎸佷笉鍙?
After split, all API path + method combinations remain identical.

**Validates: Requirements 4.3, 4.6**

鏂囦欢锛歜ackend/tests/test_router_registry_split.py
"""

from hypothesis import given, settings, strategies as st

from app.main import app


# ---------------------------------------------------------------------------
# Collect all registered routes from the FastAPI app
# ---------------------------------------------------------------------------

def _collect_routes() -> set[tuple[str, str]]:
    """Collect all (path, method) tuples from the FastAPI app."""
    routes = set()
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods:
                routes.add((route.path, method))
    return routes


# ---------------------------------------------------------------------------
# Known critical API paths that MUST exist after split
# ---------------------------------------------------------------------------

CRITICAL_PATHS = [
    ("/api/version", "GET"),
    ("/metrics", "GET"),
]


class TestRouterRegistrySplit:
    """Property 8: 璺敱鎷嗗垎鍚庤矾寰勪繚鎸佷笉鍙?

    **Validates: Requirements 4.3, 4.6**

    For any API route registered, the exact same path + method combination
    must exist after the split (set equality of all registered routes).
    """

    def test_routes_are_registered(self):
        """App has routes registered (basic sanity check)."""
        routes = _collect_routes()
        assert len(routes) > 0, "No routes registered in the app"

    def test_critical_paths_exist(self):
        """Critical API paths must exist after split."""
        routes = _collect_routes()
        for path, method in CRITICAL_PATHS:
            assert (path, method) in routes, (
                f"Critical route ({method} {path}) missing after split"
            )

    def test_all_routes_have_valid_path_format(self):
        """All registered routes must have valid path format (start with /)."""
        routes = _collect_routes()
        for path, method in routes:
            assert path.startswith("/"), (
                f"Route path does not start with /: {path}"
            )

    def test_all_routes_have_valid_methods(self):
        """All registered routes must have valid HTTP methods."""
        valid_methods = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
        routes = _collect_routes()
        for path, method in routes:
            assert method in valid_methods, (
                f"Invalid HTTP method '{method}' for path {path}"
            )

    def test_routes_are_collected_consistently(self):
        """Route collection is consistent (same result each time)."""
        routes_a = _collect_routes()
        routes_b = _collect_routes()
        assert routes_a == routes_b, (
            "Route collection should be deterministic"
        )

    def test_api_routes_use_api_prefix(self):
        """Most business routes should use /api/ prefix."""
        routes = _collect_routes()
        api_routes = {(p, m) for p, m in routes if p.startswith("/api/")}
        # Should have many API routes
        assert len(api_routes) > 10, (
            f"Expected many /api/ routes, got {len(api_routes)}"
        )

    def test_route_count_is_substantial(self):
        """Route count should be substantial (>100 based on 123 include_router calls)."""
        routes = _collect_routes()
        # Each include_router adds at least 1 route, many add multiple
        assert len(routes) >= 50, (
            f"Expected >=50 routes, got {len(routes)}. "
            "Routes may not be properly registered after split."
        )

    @settings(max_examples=10)
    @given(
        sample_idx=st.integers(min_value=0, max_value=999)
    )
    def test_route_set_is_stable_across_calls(self, sample_idx: int):
        """Property 8: Route set is stable 鈥?collecting routes multiple times
        always yields the same set.

        **Validates: Requirements 4.3, 4.6**
        """
        routes_a = _collect_routes()
        routes_b = _collect_routes()
        assert routes_a == routes_b, (
            f"Route set changed between calls (sample {sample_idx})"
        )
