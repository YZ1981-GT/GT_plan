"""旧 PM 批量复核端点退役后，同路径只由配置驱动状态机实现提供。"""
from pathlib import Path

from app.main import app


ROOT = Path(__file__).resolve().parents[2]


def test_pm_dashboard_no_longer_imports_deleted_batch_review_service():
    source = (ROOT / "backend/app/routers/pm_dashboard.py").read_text(encoding="utf-8")
    assert "BatchReviewService" not in source
    assert '"/api/projects/{project_id}/batch-review"' not in source


def test_batch_review_runtime_route_is_unique_and_uses_state_machine_router():
    endpoints = []
    for route in app.routes:
        if (
            getattr(route, "path", "") == "/api/projects/{project_id}/batch-review"
            and "POST" in (getattr(route, "methods", set()) or set())
        ):
            endpoint = route.endpoint
            endpoints.append(f"{endpoint.__module__}.{endpoint.__name__}")
    assert endpoints == ["app.routers.batch_review.batch_review"]
