"""附件项目级存储边界与公开 raw-path 路由退役守卫。"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from starlette.routing import Match

from app.services.attachment_storage_resolver import (
    inline_preview_allowed,
    plan_project_attachment,
)


def test_local_file_must_be_inside_own_project_root(tmp_path: Path) -> None:
    root = tmp_path / "attachments"
    project_a, project_b = uuid.uuid4(), uuid.uuid4()
    own = root / str(project_a) / "evidence" / "own.pdf"
    other = root / str(project_b) / "evidence" / "other.pdf"
    own.parent.mkdir(parents=True)
    other.parent.mkdir(parents=True)
    own.write_bytes(b"own")
    other.write_bytes(b"other")

    ok = plan_project_attachment(project_a, "local", str(own), root=root)
    cross = plan_project_attachment(project_a, "local", str(other), root=root)
    assert ok.kind == "local" and ok.canonical_path == own.resolve()
    assert cross.rejected and cross.canonical_path is None


def test_outside_and_unknown_scheme_are_rejected(tmp_path: Path) -> None:
    project_id = uuid.uuid4()
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    root = tmp_path / "attachments"
    assert plan_project_attachment(project_id, "local", str(outside), root=root).rejected
    assert plan_project_attachment(project_id, "local", "staged://x", root=root).rejected
    assert plan_project_attachment(project_id, "local", "", root=root).rejected


def test_symlink_escape_is_rejected(tmp_path: Path) -> None:
    project_id = uuid.uuid4()
    root = tmp_path / "attachments"
    scoped = root / str(project_id)
    scoped.mkdir(parents=True)
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"secret")
    link = scoped / "escape.pdf"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("当前环境不允许创建符号链接")
    plan = plan_project_attachment(project_id, "local", str(link), root=root)
    assert plan.rejected and plan.canonical_path is None


def test_remote_locator_and_active_content_policy(tmp_path: Path) -> None:
    project_id = uuid.uuid4()
    assert plan_project_attachment(project_id, "paperless", "paperless://documents/7", root=tmp_path).kind == "remote"
    assert plan_project_attachment(project_id, "paperless", "7", root=tmp_path).rejected
    assert inline_preview_allowed("safe.pdf") is True
    assert inline_preview_allowed("active.svg") is False
    assert inline_preview_allowed("active.HTML") is False


def test_raw_path_create_route_is_retired_and_static_health_is_reachable() -> None:
    from app.routers.attachments import router

    raw_create = [
        route for route in router.routes
        if getattr(route, "path", "") == "/api/projects/{project_id}/attachments"
        and "POST" in (getattr(route, "methods", set()) or set())
    ]
    assert raw_create == []

    scope = {
        "type": "http", "method": "GET", "path": "/api/attachments/paperless-health",
        "root_path": "", "headers": [], "query_string": b"", "scheme": "http",
    }
    matches = [route for route in router.routes if route.matches(scope)[0] == Match.FULL]
    assert matches and matches[0].endpoint.__name__ == "check_paperless_health"
