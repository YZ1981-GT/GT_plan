"""
test_ledger_import_entrypoints.py

验证 LEDGER_IMPORT_ENTRYPOINTS 常量与 validate_entrypoints 函数。
design §5, R8, AC-14, AC-23.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.ledger_import_entrypoints import (
    LEDGER_IMPORT_ENTRYPOINTS,
    EntrypointValidationError,
    validate_entrypoints,
)


# ── 1. 常量结构 ──────────────────────────────────────────

class TestEntrypointConstants:
    """LEDGER_IMPORT_ENTRYPOINTS 是非空 frozenset。"""

    def test_is_frozenset(self) -> None:
        assert isinstance(LEDGER_IMPORT_ENTRYPOINTS, frozenset)

    def test_non_empty(self) -> None:
        assert len(LEDGER_IMPORT_ENTRYPOINTS) > 0

    def test_all_entries_have_required_fields(self) -> None:
        for entry in LEDGER_IMPORT_ENTRYPOINTS:
            assert entry.path, f"path 为空: {entry}"
            assert entry.method in ("GET", "POST", "PUT", "DELETE"), f"非法 method: {entry.method}"
            assert entry.kind in ("preview", "detect", "submit", "retired", "status", "recovery")
            assert entry.description

    def test_contains_three_submit_entries(self) -> None:
        submits = [e for e in LEDGER_IMPORT_ENTRYPOINTS if e.kind == "submit"]
        assert len(submits) == 3

    def test_contains_retired_entries(self) -> None:
        retired = [e for e in LEDGER_IMPORT_ENTRYPOINTS if e.kind == "retired"]
        assert len(retired) >= 3  # account-chart/import, /import, incremental/apply

    def test_contains_detect_entries(self) -> None:
        detects = [e for e in LEDGER_IMPORT_ENTRYPOINTS if e.kind == "detect"]
        assert len(detects) >= 2

    def test_no_duplicate_paths(self) -> None:
        paths = [(e.path, e.method) for e in LEDGER_IMPORT_ENTRYPOINTS]
        assert len(paths) == len(set(paths)), "存在重复的 (path, method) 对"


# ── 2. validate_entrypoints 校验逻辑 ─────────────────────

def _mock_app(routes: list[dict]) -> SimpleNamespace:
    """构造简单的模拟 app 对象。"""
    mock_routes = []
    for r in routes:
        mock_routes.append(SimpleNamespace(path=r["path"], methods=r.get("methods", {"GET"})))
    return SimpleNamespace(routes=mock_routes)


class TestValidateEntrypoints:

    def test_all_registered_paths_present_passes(self) -> None:
        """当 app.routes 包含所有已注册路径时不抛异常。"""
        routes = [{"path": e.path} for e in LEDGER_IMPORT_ENTRYPOINTS]
        app = _mock_app(routes)
        # 不应抛异常
        validate_entrypoints(app)

    def test_missing_registered_path_raises(self) -> None:
        """已注册路径不在 app.routes 中时抛异常。"""
        # 给一个空 app
        app = _mock_app([])
        with pytest.raises(EntrypointValidationError) as exc_info:
            validate_entrypoints(app)
        assert exc_info.value.missing

    def test_unregistered_import_path_raises(self) -> None:
        """app.routes 包含未注册的导入相关路由时抛异常。"""
        routes = [{"path": e.path} for e in LEDGER_IMPORT_ENTRYPOINTS]
        # 加一个未注册的导入相关路由
        routes.append({"path": "/api/projects/{project_id}/ledger-import/secret-backdoor"})
        app = _mock_app(routes)
        with pytest.raises(EntrypointValidationError) as exc_info:
            validate_entrypoints(app)
        assert exc_info.value.unregistered

    def test_non_import_extra_route_ignored(self) -> None:
        """非导入相关的额外路由不触发异常。"""
        routes = [{"path": e.path} for e in LEDGER_IMPORT_ENTRYPOINTS]
        routes.append({"path": "/api/health"})
        routes.append({"path": "/api/users/me/display-preferences"})
        app = _mock_app(routes)
        validate_entrypoints(app)
