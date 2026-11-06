"""
test_export_surface_registry.py

验证 EXPORT_SURFACE_REGISTRY 结构与 validate_registry(app) 闭合性。
design §9, R9, AC-20, AC-23.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.export_surface_registry import (
    EXPORT_SURFACE_REGISTRY,
    ExportSurfaceEntry,
    RegistryValidationError,
    validate_registry,
)


# ── helpers ───────────────────────────────────────────────

def _mock_app(routes: list[dict]) -> SimpleNamespace:
    mock_routes = []
    for r in routes:
        mock_routes.append(SimpleNamespace(path=r["path"], methods=r.get("methods", {"GET"})))
    return SimpleNamespace(routes=mock_routes)


# ── 1. 注册表结构 ────────────────────────────────────────

class TestRegistryStructure:

    def test_non_empty(self) -> None:
        assert len(EXPORT_SURFACE_REGISTRY) > 0

    def test_all_entries_have_required_fields(self) -> None:
        for key, entry in EXPORT_SURFACE_REGISTRY.items():
            assert isinstance(entry, ExportSurfaceEntry), f"{key} 不是 ExportSurfaceEntry"
            assert entry.path, f"{key} 缺少 path"
            assert entry.method in ("GET", "POST", "PUT", "DELETE"), f"{key} 非法 method"
            assert entry.classification in ("formal", "data_exchange", "template", "non_amount")
            assert entry.description

    def test_formal_entries_exist(self) -> None:
        formal = [k for k, v in EXPORT_SURFACE_REGISTRY.items() if v.classification == "formal"]
        assert len(formal) >= 5, "formal 分类条目应至少含试算表、报表、附注、底稿、PDF"

    def test_data_exchange_entries_exist(self) -> None:
        de = [k for k, v in EXPORT_SURFACE_REGISTRY.items() if v.classification == "data_exchange"]
        assert len(de) >= 1

    def test_no_duplicate_paths(self) -> None:
        paths = [v.path for v in EXPORT_SURFACE_REGISTRY.values()]
        assert len(paths) == len(set(paths)), "存在重复的 path"


# ── 2. validate_registry 闭合性 ──────────────────────────

class TestValidateRegistry:

    def test_all_registered_present_passes(self) -> None:
        """app.routes 包含全部注册路径时不抛异常。"""
        routes = [{"path": e.path} for e in EXPORT_SURFACE_REGISTRY.values()]
        app = _mock_app(routes)
        validate_registry(app)

    def test_missing_registered_path_raises(self) -> None:
        """已注册路径不在 app.routes 中时抛异常。"""
        app = _mock_app([])
        with pytest.raises(RegistryValidationError) as exc_info:
            validate_registry(app)
        assert exc_info.value.missing

    def test_unregistered_export_path_raises(self) -> None:
        """app.routes 包含未注册的导出路由时抛异常。"""
        routes = [{"path": e.path} for e in EXPORT_SURFACE_REGISTRY.values()]
        routes.append({"path": "/api/projects/{project_id}/export-secret"})
        app = _mock_app(routes)
        with pytest.raises(RegistryValidationError) as exc_info:
            validate_registry(app)
        assert exc_info.value.unregistered

    def test_non_export_extra_route_ignored(self) -> None:
        """非导出相关的额外路由不触发异常。"""
        routes = [{"path": e.path} for e in EXPORT_SURFACE_REGISTRY.values()]
        routes.append({"path": "/api/health"})
        routes.append({"path": "/api/projects/{project_id}/config"})
        routes.append({"path": "/api/users/me/display-preferences"})
        app = _mock_app(routes)
        validate_registry(app)

    def test_classification_coverage(self) -> None:
        """四种分类至少各出现一次。"""
        classes = {v.classification for v in EXPORT_SURFACE_REGISTRY.values()}
        assert "formal" in classes
        assert "data_exchange" in classes
        assert "template" in classes
        assert "non_amount" in classes
