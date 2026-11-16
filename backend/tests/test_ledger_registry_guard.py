"""
test_ledger_registry_guard.py

账套两个 registry 接入唯一守卫（spec platform-global-display-settings-closure 11B）。

守卫要点（对应 2026-11-14 复核记录的模式 1/2/4）：
1. **空注册表 = 判据恒绿** ⇒ 必须判失败，不能算「没有违规」。
2. **未与真实 app.routes 对拍** ⇒ 必须判失败（`routes_checked=False`）。
3. **缺键** ⇒ 必须判失败（design §8.1 阶段 B 起为必含键）。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.services.ledger_registry_guard import (
    LEDGER_REGISTRY_SCHEMA_VERSION,
    collect_ledger_registry_results,
    failures,
)

_BACKEND = Path(__file__).resolve().parents[1]


# ── 1. 真实注册表（不 mock）─────────────────────────────────

class TestRealRegistries:
    def test_read_surface_summary_has_no_errors(self) -> None:
        results = collect_ledger_registry_results(None)
        read = results["ledger_read_surface_results"]
        assert read["declared"] > 0
        assert read["errors"] == []
        assert read["missing_module"] == []
        assert read["missing_symbol"] == []
        assert len(read["valid"]) == read["declared"]

    def test_read_surface_covers_four_tables(self) -> None:
        read = collect_ledger_registry_results(None)["ledger_read_surface_results"]
        assert set(read["tables"]) == {
            "tb_balance", "tb_ledger", "tb_aux_balance", "tb_aux_ledger",
        }

    def test_entrypoint_summary_without_app_is_failure(self) -> None:
        """不传 app ⇒ 未与真实路由对拍 ⇒ 必须判失败（不能静默通过）。"""
        results = collect_ledger_registry_results(None)
        ep = results["ledger_import_entrypoint_results"]
        assert ep["routes_checked"] is False
        issues = failures(results)
        assert any("未与真实 app.routes" in i for i in issues)

    def test_schema_version_is_pinned(self) -> None:
        assert LEDGER_REGISTRY_SCHEMA_VERSION == 1
        results = collect_ledger_registry_results(None)
        assert results["ledger_read_surface_results"]["schema_version"] == 1


# ── 2. 空注册表 = 恒绿 ⇒ 判失败 ────────────────────────────

class TestEmptyRegistryFails:
    def test_empty_read_surface_is_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.services.ledger_read_surfaces as mod

        monkeypatch.setattr(mod, "LEDGER_TABLE_READ_SURFACES", {})
        results = collect_ledger_registry_results(None)
        read = results["ledger_read_surface_results"]
        assert read["declared"] == 0
        assert read["errors"]
        issues = failures(results)
        assert any("ledger_read_surface_results.declared == 0" in i for i in issues)

    def test_empty_entrypoints_is_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.services.ledger_import_entrypoints as mod

        monkeypatch.setattr(mod, "LEDGER_IMPORT_ENTRYPOINTS", frozenset())
        results = collect_ledger_registry_results(None)
        ep = results["ledger_import_entrypoint_results"]
        assert ep["declared"] == 0
        assert ep["errors"]
        issues = failures(results)
        assert any("ledger_import_entrypoint_results.declared == 0" in i for i in issues)


# ── 3. 真实 app 对拍（较慢，单列）────────────────────────────

class TestWithRealApp:
    def test_real_app_entrypoints_are_closed(self) -> None:
        """真实 app.routes 与登记表双向闭合（unregistered/missing/retired 均空）。"""
        from app.main import app

        results = collect_ledger_registry_results(app)
        ep = results["ledger_import_entrypoint_results"]
        assert ep["routes_checked"] is True
        assert ep["unregistered"] == []
        assert ep["missing"] == []
        assert ep["retired_not_410"] == []


# ── 4. CLI 输出契约（design §8.1）────────────────────────────

class TestCliOutputContract:
    def test_cli_json_contains_required_keys(self, tmp_path: Path) -> None:
        out = tmp_path / "cli.json"
        proc = subprocess.run(
            [sys.executable, "-m", "scripts.check.frontend_amount_guard.cli",
             "--check", "--output", str(out)],
            cwd=str(_BACKEND), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=900,
            env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
        )
        # 🔴 断言 stdout 有内容：只判 returncode 会漏掉解码失败导致 stdout=None 的假绿
        assert proc.stdout is not None and proc.stdout.strip(), (
            f"CLI 无输出（stderr={proc.stderr!r}）"
        )
        assert proc.returncode == 0, f"CLI 失败：{proc.stdout}\n{proc.stderr}"
        data = json.loads(out.read_text(encoding="utf-8"))
        # design §8.1 阶段 B 起的必含键
        for key in ("schema_version", "ledger_read_surface_results",
                    "ledger_import_entrypoint_results", "scopes", "total_candidates"):
            assert key in data, f"缺键 {key}"
        assert data["schema_version"] >= 2
        assert data["ledger_read_surface_results"]["declared"] > 0
        assert data["ledger_import_entrypoint_results"]["routes_checked"] is True


# ── 5. 正式导出出口闭集（11C / design §8.1 阶段 C）──────────────


class TestExportSurfaceSummary:
    def test_summary_has_four_classifications(self) -> None:
        """四个分类都必须至少有一条登记（否则某一类完全不受检）。"""
        from app.services.ledger_registry_guard import collect_all_registry_results

        results = collect_all_registry_results(None)
        ex = results["export_surface_results"]
        assert ex["declared"] > 0
        assert set(ex["by_classification"]) == {
            "formal", "data_exchange", "template", "non_amount",
        }
        # 传 None 时「未提供 app」是**预期**的失败信号（不是缺陷）；
        # 真正要判的是「四分类缺失」这类静态问题不在 errors 里。
        assert not any("没有任何登记出口" in e for e in ex["errors"])

    def test_without_app_is_failure(self) -> None:
        """不传 app ⇒ 未与真实路由对拍 ⇒ 必须判失败。"""
        from app.services.ledger_registry_guard import (
            all_failures,
            collect_all_registry_results,
        )

        results = collect_all_registry_results(None)
        ex = results["export_surface_results"]
        assert ex["routes_checked"] is False
        issues = all_failures(results)
        assert any("未与真实 app.routes" in i for i in issues)

    def test_empty_registry_is_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.services import export_surface_registry as mod
        from app.services.ledger_registry_guard import (
            all_failures,
            collect_all_registry_results,
        )

        monkeypatch.setattr(mod, "EXPORT_SURFACE_REGISTRY", {})
        results = collect_all_registry_results(None)
        ex = results["export_surface_results"]
        assert ex["declared"] == 0
        assert ex["errors"]
        issues = all_failures(results)
        assert any("export_surface_results.declared == 0" in i for i in issues)

    def test_missing_classification_is_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """删掉某一分类的全部出口 ⇒ 必须点名（该分类完全不受检）。"""
        from app.services import export_surface_registry as mod
        from app.services.ledger_registry_guard import collect_all_registry_results

        only_formal = {
            k: v for k, v in mod.EXPORT_SURFACE_REGISTRY.items()
            if v.classification == "formal"
        }
        monkeypatch.setattr(mod, "EXPORT_SURFACE_REGISTRY", only_formal)
        results = collect_all_registry_results(None)
        ex = results["export_surface_results"]
        assert ex["errors"]
        assert any("没有任何登记出口" in e for e in ex["errors"])

    def test_known_drift_is_hard_failure(self) -> None:
        """漂移（unregistered / missing）必须进入硬失败清单。

        🔴 2026-11-16 反转：变更前本条断言的是「known_drift 不应进入硬失败清单」，
        理由是 memory ㉗「恒红门禁等于没有门禁」。但该规则针对的是**永假判据**
        （时间戳 / 随机数进判据），而这里是**已知待办** —— 结果是三层门禁同时
        失效：`test_missing_is_zero` 只看 missing、本函数跳过 known_drift、
        `validate_registry` 的抛异常没人接。实测把元数据口径过滤整个删掉
        （让 status / history / manifest 都算导出出口），8 条变异里 3 条存活。

        漂移已清零（303 → 0），现在两个方向都必须阻断：
        - `unregistered` = 实现了没登记（新加导出端点漏登记）
        - `missing` = 登记了没实现（曾导致前端点一次 404）
        """
        from app.main import app
        from app.services.export_surface_registry import (
            EXPORT_SURFACE_REGISTRY,
            ExportSurfaceEntry,
        )
        from app.services.ledger_registry_guard import (
            all_failures,
            collect_all_registry_results,
        )

        # 先确认基线干净（否则下面的注入证明不了任何事）
        baseline = collect_all_registry_results(app)
        assert baseline["export_surface_results"]["known_drift"] == []
        assert all_failures(baseline) == []

        # 注入一条「登记了但没实现」⇒ missing 非空
        key = "_probe_missing_entry"
        try:
            EXPORT_SURFACE_REGISTRY[key] = ExportSurfaceEntry(
                path="/api/_probe/never-implemented/export",
                method="GET",
                classification="formal",
                description="probe",
            )
            results = collect_all_registry_results(app)
            ex = results["export_surface_results"]
            assert ex["known_drift"], "注入后 known_drift 必须非空"
            assert ex["errors"], "注入后 errors 必须非空（不再只报告）"

            issues = all_failures(results)
            assert any("missing" in i for i in issues), (
                f"missing 必须进入硬失败清单，实得 {issues}"
            )
            assert any("known_drift" in i for i in issues), (
                f"known_drift 非空本身也必须进入硬失败清单，实得 {issues}"
            )
        finally:
            EXPORT_SURFACE_REGISTRY.pop(key, None)

        # 还原后必须重新干净
        restored = collect_all_registry_results(app)
        assert restored["export_surface_results"]["known_drift"] == []
        assert all_failures(restored) == []

    def test_metadata_filter_weakening_breaks_closure(self) -> None:
        """反向自检：弱化元数据口径必须让闭合判定失败。

        🔴 这是 `known_drift` 改硬失败后才成立的判据。变更前：把
        `is_metadata_only_export_path` 整个删掉（让 /status、/history、
        /manifest 都算导出出口）时，全部用例仍然全绿 —— 因为多出来的
        8 条「未登记」全被降级进 known_drift，没人检查它。
        """
        from app.main import app
        from app.services import export_surface_registry as reg
        from app.services.ledger_registry_guard import (
            all_failures,
            collect_all_registry_results,
        )

        baseline = collect_all_registry_results(app)
        assert all_failures(baseline) == [], "基线必须先干净"

        original = reg.is_metadata_only_export_path
        try:
            # 弱化：任何路径都不算元数据 ⇒ 8 条元数据路由变成「未登记的导出出口」
            reg.is_metadata_only_export_path = lambda _p: False
            results = collect_all_registry_results(app)
            ex = results["export_surface_results"]
            assert ex["unregistered"], (
                "弱化口径后 unregistered 必须非空（否则说明 _is_export_path "
                "没调用它，或判据没扫到）"
            )
            issues = all_failures(results)
            assert any("unregistered" in i for i in issues), (
                f"unregistered 必须进入硬失败清单，实得 {issues}"
            )
        finally:
            reg.is_metadata_only_export_path = original

        restored = collect_all_registry_results(app)
        assert all_failures(restored) == []


class TestCliSchemaVersion3:
    def test_schema_version_is_three(self) -> None:
        from scripts.check.frontend_amount_guard import cli

        assert cli._CLI_SCHEMA_VERSION == 3

    def test_cli_json_contains_export_surface_key(self, tmp_path: Path) -> None:
        """design §8.1 阶段 C 起 `export_surface_results` 为必含键。"""
        out = tmp_path / "cli.json"
        proc = subprocess.run(
            [sys.executable, "-m", "scripts.check.frontend_amount_guard.cli",
             "--check", "--output", str(out)],
            cwd=str(_BACKEND), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=900,
            env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
        )
        assert proc.stdout is not None and proc.stdout.strip()
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["schema_version"] >= 3
        assert "export_surface_results" in data
        assert data["export_surface_results"]["declared"] > 0
        assert data["export_surface_results"]["routes_checked"] is True
