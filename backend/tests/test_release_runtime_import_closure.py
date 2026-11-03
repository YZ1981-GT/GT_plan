"""干净候选树的应用导入、路由唯一性与迁移号闭合守卫。"""

from __future__ import annotations

import re
from pathlib import Path

from starlette.requests import Request


def test_application_imports_with_all_registered_routers():
    from app.main import app

    assert len(app.routes) > 2000
    assert any(
        getattr(route, "path", "") == "/api/projects/{project_id}/batch-review"
        and "POST" in (getattr(route, "methods", set()) or set())
        and route.endpoint.__module__ == "app.routers.batch_review"
        for route in app.routes
    )


def test_retired_pm_batch_review_does_not_shadow_state_machine():
    import app.routers.pm_dashboard as pm_dashboard

    assert not hasattr(pm_dashboard, "batch_review")
    assert not hasattr(pm_dashboard, "BatchReviewRequest")


def test_forward_migration_versions_are_unique():
    migration_dir = Path(__file__).resolve().parents[1] / "migrations"
    by_version: dict[int, list[str]] = {}
    for path in migration_dir.glob("V*.sql"):
        match = re.match(r"V(\d+)__", path.name)
        if match:
            by_version.setdefault(int(match.group(1)), []).append(path.name)
    duplicates = {version: names for version, names in by_version.items() if len(names) > 1}
    assert duplicates == {}


def test_display_preferences_audit_redactor_never_logs_values_or_page_keys():
    from app.middleware.audit_log import _redact_if_display_prefs

    scope = {
        "type": "http",
        "method": "PATCH",
        "path": "/api/users/me/display-preferences",
        "headers": [],
        "query_string": b"",
        "server": ("test", 80),
        "client": ("127.0.0.1", 1234),
        "scheme": "http",
    }
    request = Request(scope)
    request.state.audit_changed_fields = ["fixed_columns", "font_size"]
    response = {
        "code": 200,
        "data": {
            "revision": 7,
            "font_size": "lg",
            "fixed_columns": {"project:secret-page": {"columns": ["amount"]}},
        },
    }

    redacted = _redact_if_display_prefs(
        "PATCH", "/api/users/me/display-preferences", response, request
    )

    assert redacted == {
        "revision": 7,
        "changed_fields": ["fixed_columns", "font_size"],
    }
    text = repr(redacted)
    assert "secret-page" not in text
    assert "amount" not in text
    assert "lg" not in text
