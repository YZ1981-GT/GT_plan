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
        """retired 必须是**具名**的三条真实退役端点。

        演进轨迹（保留，避免再次来回改）：

        - 原断言 `len(retired) >= 3`，把 `/api/projects/{project_id}/import`
          也算进去了，但当时那条端点实际仍执行完整导入
          （`data_import.upload_and_import`）⇒ **错标**；
        - 中间一轮改成具名两条（只留 account-chart / incremental apply），
          并把 `/import` 改登为 `preview`（描述「待裁决是否退役」）；
        - 2026-11-16 按 R8 / design §5 裁决：`/api/projects/{project_id}/import`
          **正式退役**，函数体固定 410 `LEDGER_IMPORT_MOVED_TO_CONFIRMED_JOB`
          且不再 import/call 任何 import service ⇒ 回到 retired，共三条。

        用**具名集合**而不是数字，是因为数字无法表达「哪一条该在 / 不该在」。
        """
        retired_paths = {e.path for e in LEDGER_IMPORT_ENTRYPOINTS if e.kind == "retired"}
        assert retired_paths == {
            "/api/projects/{project_id}/account-chart/import",
            "/api/projects/{project_id}/import",
            "/api/projects/{project_id}/ledger-data/incremental/apply",
        }

    def test_retired_entries_actually_raise_410(self) -> None:
        """对真实 `app.main.app` 跑一次：登记为 retired 的端点必须真的返回 410。

        这是 spec platform-global-display-settings-closure 任务 8「复核记录模式②：
        声明为 retired 但真的在跑」的专用判据。此前 `validate_entrypoints`
        只校验「路径存在」，于是 `/account-chart/import` 还在 POST 写库、
        登记表却写 retired，校验全绿。
        """
        from app.main import app

        validate_entrypoints(app)  # 抛异常即为失败

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
        mock_routes.append(SimpleNamespace(path=r["path"], methods=r.get("methods")))
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

    def test_method_mismatch_is_not_hidden_by_same_path(self) -> None:
        """同一路径的错误 method 必须进入未注册/缺失闭集。"""
        routes = [
            {"path": e.path, "methods": {e.method}}
            for e in LEDGER_IMPORT_ENTRYPOINTS
        ]
        routes.append({
            "path": "/api/projects/{project_id}/account-chart/import",
            "methods": {"GET"},
        })
        app = _mock_app(routes)
        with pytest.raises(EntrypointValidationError) as exc_info:
            validate_entrypoints(app)
        assert "GET /api/projects/{}/account-chart/import" in exc_info.value.unregistered
        assert "POST /api/projects/{}/account-chart/import" not in exc_info.value.unregistered

    def test_non_import_extra_route_ignored(self) -> None:
        """非导入相关的额外路由不触发异常。"""
        routes = [{"path": e.path} for e in LEDGER_IMPORT_ENTRYPOINTS]
        routes.append({"path": "/api/health"})
        routes.append({"path": "/api/users/me/display-preferences"})
        app = _mock_app(routes)
        validate_entrypoints(app)

# ── 3. 「声明为 retired 但真的在跑」专用判据（模式②守卫） ─────────────

class TestRetiredActuallyReturns410:
    """校验函数必须真的能抓到「登记 retired 但处理函数不返回 410」。

    🔴 这一组是把 `_collect_retired_not_410` 本身钉住：
    删掉它（变异 M3）后，`test_contains_retired_entries` 与
    `test_retired_endpoint_returns_410_with_error_code` 仍然全绿
    （它们一个只看注册表、一个只看函数体 AST），
    于是「判据存在但没生效」又会静默复活 —— 本轮变异实测坐实。
    """

    def test_collect_flags_endpoint_that_does_business_first(self) -> None:
        """处理函数先做业务、末尾才 410 ⇒ 必须被点名（那条路径仍会写数据）。"""
        from app.services.ledger_import_entrypoints import _collect_retired_not_410

        def _not_retired_import():  # 模拟「还真的在导入」
            return {"ok": True}

        app = SimpleNamespace(
            routes=[
                SimpleNamespace(
                    path="/api/projects/{project_id}/account-chart/import",
                    endpoint=_not_retired_import,
                )
            ]
        )
        offenders = _collect_retired_not_410(app)
        assert offenders == ["/api/projects/{project_id}/account-chart/import"]

    def test_collect_accepts_endpoint_that_raises_410_first(self) -> None:
        """第一条语句就 raise HTTPException(410) ⇒ 不点名（正面判据）。"""
        from fastapi import HTTPException

        from app.services.ledger_import_entrypoints import _collect_retired_not_410

        def _retired_import():
            raise HTTPException(status_code=410, detail={"error_code": "X"})

        app = SimpleNamespace(
            routes=[
                SimpleNamespace(
                    path="/api/projects/{project_id}/account-chart/import",
                    endpoint=_retired_import,
                )
            ]
        )
        assert _collect_retired_not_410(app) == []

    def test_collect_skips_undeterminable_endpoint(self) -> None:
        """取不到 endpoint（假路由 / 测试替身）⇒ 不点名（不能把替身判成缺陷）。"""
        from app.services.ledger_import_entrypoints import _collect_retired_not_410

        app = SimpleNamespace(
            routes=[SimpleNamespace(path="/api/projects/{project_id}/account-chart/import")]
        )
        assert _collect_retired_not_410(app) == []


# ── 4. 路径域判据必须收窄（防 22 条假阳） ──────────────────────────────

class TestImportPathScope:
    """`_is_ledger_import_path` 的收窄必须被钉住。

    🔴 原判据 `endswith("/import") and "/projects/" in path` 会把
    `adjustments/import`、`bulk-tab/import`、`review-workflow/{}/import`
    等别的业务域全抓成「未登记」—— 对真实 app 跑出 22 条假阳。
    假阳的代价是让人误以为注册表严重欠登记（真实欠登记是 18 条，
    另一批），属于「扫描器命中 ≠ 本域有缺陷」（memory 铁律 ㉒）。
    """

    def test_excludes_other_business_domains(self) -> None:
        from app.services.ledger_import_entrypoints import _is_ledger_import_path

        for path in [
            "/api/projects/{project_id}/adjustments/import",
            "/api/projects/{project_id}/adjustments/import/preview",
            "/api/projects/{project_id}/adjustments/reclassification/import",
            "/api/projects/{project_id}/bulk-tab/import",
            "/api/projects/{project_id}/review-workflow/{year}/import",
            "/api/projects/{project_id}/account-chart/import-reset",
            "/api/import-templates/{template_id}/download",
            "/api/projects/{project_id}/import-intelligence/overview",
        ]:
            assert not _is_ledger_import_path(path), f"不应判为账套导入域: {path}"

    def test_includes_real_ledger_import_paths(self) -> None:
        from app.services.ledger_import_entrypoints import _is_ledger_import_path

        for path in [
            "/api/projects/{project_id}/account-chart/import",
            "/api/projects/{project_id}/ledger-import/detect",
            "/api/projects/{project_id}/ledger-import/jobs/{job_id}/retry",
            "/api/projects/{project_id}/ledger-import/datasets/active",
            "/api/projects/{project_id}/ledger-data/incremental/apply",
            "/api/projects/{project_id}/import",
            "/api/ledger-import/validation-rules",
        ]:
            assert _is_ledger_import_path(path), f"应判为账套导入域: {path}"
def test_validate_entrypoints_raises_when_retired_endpoint_runs() -> None:
        """`validate_entrypoints` 必须把 retired_not_410 报出来。

        🔴 这条是 M6 变异存活后补的：上面三条只测 `_collect_retired_not_410`
        这个辅助函数，而真正被生产 / 测试调用的入口是 `validate_entrypoints`。
        把 `validate_entrypoints` 里的 retired 判定整段删掉后，
        辅助函数的三条用例仍然全绿（它们不经过 validate）⇒ 又一条「判据存在但没生效」。
        这里直接用「假路由 + 违规 endpoint」，断言 validate 真的抛错。
        """

        def _runs_business():  # 登记 retired 却真的在导入
            return {"ok": True}

        app = SimpleNamespace(
            routes=[
                SimpleNamespace(
                    path="/api/projects/{project_id}/account-chart/import",
                    endpoint=_runs_business,
                )
            ]
        )
        with pytest.raises(EntrypointValidationError) as exc_info:
            validate_entrypoints(app)
        assert exc_info.value.retired_not_410 == [
            "/api/projects/{project_id}/account-chart/import"
        ]


# ── 5. 旧同步 POST 退役：错误码字面量必须被钉住 ─────────────────────

class TestRetiredSyncPostsRaise410WithExactCode:
    """三条 retired 端点必须**真的**返回 410 且错误码逐字正确。

    🔴 这是 M12 变异存活后补的：`_collect_retired_not_410` 只校验
    「第一条语句是 raise HTTPException(status_code=410)」，**不校验 detail 里的
    error_code**。于是把 `LEDGER_IMPORT_MOVED_TO_CONFIRMED_JOB` 改成别的字符串，
    全部守卫仍然全绿 —— 而前端是按 error_code 分支处理的（换码等于换契约）。
    """

    def test_old_generic_import_post_is_gone_with_exact_code(self) -> None:
        import asyncio
        import uuid as _uuid

        from fastapi import HTTPException

        from app.routers import data_import

        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                data_import.upload_and_import(
                    project_id=_uuid.UUID("22222222-3333-4444-5555-666666666666"),
                    current_user=SimpleNamespace(id="u"),
                )
            )
        assert exc.value.status_code == 410
        assert exc.value.detail["error_code"] == "LEDGER_IMPORT_MOVED_TO_CONFIRMED_JOB"

    def test_old_account_chart_import_post_has_exact_code(self) -> None:
        """源码层断言（端点签名带 Form/File 依赖，直接调需要造一堆占位）。"""
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[1] / "app/routers/account_chart.py"
        ).read_text(encoding="utf-8")
        assert '"error_code": "LEDGER_IMPORT_MOVED_TO_CONFIRMED_JOB"' in source

    def test_old_incremental_apply_has_exact_code(self) -> None:
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[1] / "app/routers/ledger_data.py"
        ).read_text(encoding="utf-8")
        assert '"error_code": "INCREMENTAL_APPLY_MOVED_TO_IMPORT_JOB"' in source
        # 旧码不得残留（否则前端按旧码分支仍能命中，等于两套契约并存）
        assert '"error_code": "INCREMENTAL_APPLY_RETIRED"' not in source

    def test_retired_sync_posts_do_not_call_import_services(self) -> None:
        """函数体不得 import/call 任何 import service 或 writer（AST 判据）。"""
        import ast
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        forbidden = {
            "start_import",
            "start_import_streaming",
            "run_account_chart_import",
            "submit_import_job",
        }
        for rel, func_name in (
            ("app/routers/data_import.py", "upload_and_import"),
            ("app/routers/account_chart.py", "import_client_chart"),
        ):
            tree = ast.parse((root / rel).read_text(encoding="utf-8"))
            func = next(
                (
                    n
                    for n in ast.walk(tree)
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and n.name == func_name
                ),
                None,
            )
            assert func is not None, f"{rel} 找不到 {func_name}"
            called = {
                getattr(n.func, "id", None) or getattr(n.func, "attr", None)
                for n in ast.walk(func)
                if isinstance(n, ast.Call)
            }
            assert not (called & forbidden), f"{func_name} 仍在调用 {called & forbidden}"
