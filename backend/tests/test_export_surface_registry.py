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
        # 🔴 只造**非退役**条目的路由：`retired=True` 的条目现算确认无真实路由，
        # 把它们造进 mock 会让 validate_registry 判成「未注册」（口径反转）。
        routes = [
            {"path": e.path}
            for e in EXPORT_SURFACE_REGISTRY.values()
            if not e.retired
        ]
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
        routes = [
            {"path": e.path}
            for e in EXPORT_SURFACE_REGISTRY.values()
            if not e.retired
        ]
        routes.append({"path": "/api/projects/{project_id}/export-secret"})
        app = _mock_app(routes)
        with pytest.raises(RegistryValidationError) as exc_info:
            validate_registry(app)
        assert exc_info.value.unregistered

    def test_non_export_extra_route_ignored(self) -> None:
        """非导出相关的额外路由不触发异常。"""
        routes = [
            {"path": e.path}
            for e in EXPORT_SURFACE_REGISTRY.values()
            if not e.retired
        ]
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

    def test_duplicate_normalized_path_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """同一路由被登记两次（即使参数名不同）必须打红。"""
        key, entry = next(iter(EXPORT_SURFACE_REGISTRY.items()))
        duplicate_path = entry.path.replace("{project_id}", "{another_project_id}")
        monkeypatch.setitem(
            EXPORT_SURFACE_REGISTRY,
            f"{key}_duplicate",
            ExportSurfaceEntry(
                path=duplicate_path,
                method=entry.method,
                classification=(
                    "data_exchange"
                    if entry.classification != "data_exchange"
                    else "formal"
                ),
                description="故障注入：重复登记同一归一化路径",
            ),
        )
        app = _mock_app(
            [
                {"path": item.path}
                for item in EXPORT_SURFACE_REGISTRY.values()
                if not item.retired
            ]
        )

        with pytest.raises(RegistryValidationError) as exc_info:
            validate_registry(app)

        assert exc_info.value.duplicate_classification
        assert "keys:" in exc_info.value.duplicate_classification[0]


# ── 闭合性棘轮（spec platform-global-display-settings-closure 任务 10 / AC-20）──
#
# 🔴 背景：`EXPORT_SURFACE_REGISTRY` 里曾挂 12 条**从未存在过**的路径
# （`missing=12`），而其中第一条就是**活的用户缺陷** —— 前端
# `views/TrialBalance.vue` 的「导出」按钮一直在调 `/trial-balance/export`，
# 后端从来没实现 ⇒ 点一次 404。其余 11 条同样「注册表登记 ≠ 路由存在」。
#
# 这组守卫把「登记了就必须真的存在」变成自动可检出的判据：
# 1. 每条**非 retired** 条目必须能在 `app.routes` 里找到（方法也要对）；
# 2. `missing` 必须为 **0**（不允许回升）；
# 3. `retired=True` 的条目**必须真的没有路由** —— 否则「退役」被当成
#    「删不掉就标退役」的后门，真实路由反而脱管。


class TestRegistryClosureRatchet:
    """注册表与实际路由的闭合性棘轮（只许变好）。"""

    def test_every_non_retired_entry_has_real_route(self) -> None:
        """每条非退役条目必须真的挂在 `app.routes` 上，且方法一致。

        只断言「注册表非空」会漏掉整类缺陷：登记齐全但路由从未实现。
        """
        from app.main import app

        actual: set[tuple[str, str]] = set()
        for r in app.routes:
            p = getattr(r, "path", None)
            if not p:
                continue
            for m in getattr(r, "methods", None) or set():
                actual.add((p, m))

        missing: list[str] = []
        for key, entry in EXPORT_SURFACE_REGISTRY.items():
            if entry.retired:
                continue
            if (entry.path, entry.method) not in actual:
                missing.append(f"{key}: {entry.method} {entry.path}")

        assert not missing, f"注册表登记但无真实路由: {missing}"

    def test_retired_entries_really_have_no_route(self) -> None:
        """退役条目必须真的没有路由 —— 防止「删不掉就标退役」掩盖真实出口。"""
        from app.main import app

        actual_paths = {getattr(r, "path", None) for r in app.routes}
        offenders = [
            f"{key}: {entry.path}"
            for key, entry in EXPORT_SURFACE_REGISTRY.items()
            if entry.retired and entry.path in actual_paths
        ]
        assert not offenders, (
            f"标了 retired 但路由真实存在（应从 retired 撤下并参与闭合）: {offenders}"
        )

    def test_missing_is_zero(self) -> None:
        """`missing` 必须为 0（原 12，2026-11-16 已逐条治理完毕）。

        🔴 这是一条**棘轮**：任何新增「登记了但没实现」的路径都会打红。
        """
        from app.main import app

        try:
            validate_registry(app)
        except RegistryValidationError as exc:
            assert not exc.missing, f"注册表 missing 不为 0: {exc.missing}"
            # unregistered 是既有的历史漂移（303 条，属独立工作量），
            # 本判据只管 missing。
            return

    def test_retired_flag_defaults_false(self) -> None:
        """`retired` 默认 False —— 否则新加条目会静默不参与闭合判定。"""
        entry = ExportSurfaceEntry(
            path="/api/x/export",
            method="GET",
            classification="formal",
            description="probe",
        )
        assert entry.retired is False
