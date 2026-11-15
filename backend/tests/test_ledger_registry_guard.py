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

    def test_known_drift_is_not_hard_failure(self) -> None:
        """既有漂移记 `known_drift`，不硬失败（memory ㉗：恒红门禁等于没有门禁）。"""
        from app import main  # noqa: F401 — 构建真实 app
        from app.services.ledger_registry_guard import (
            all_failures,
            collect_all_registry_results,
        )

        from app.main import app

        results = collect_all_registry_results(app)
        ex = results["export_surface_results"]
        assert ex["routes_checked"] is True
        # 漂移存在时记 known_drift，但 all_failures 不得因它而失败
        issues = all_failures(results)
        drift_issues = [i for i in issues if "unregistered" in i or "missing:" in i]
        assert drift_issues == [], (
            "known_drift 不应进入硬失败清单；它只作报告"
        )


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
