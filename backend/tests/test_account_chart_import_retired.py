"""`/account-chart/import` 必须真的返回 410（端点级验证）。

spec platform-global-display-settings-closure 任务 8 / 复核记录模式②：
「声明为 retired 但真的在跑」—— 该端点原先仍 `POST` 且执行
`LedgerImportApplicationService.run_account_chart_import`，会真的写科目表与四表，
而 `LEDGER_IMPORT_ENTRYPOINTS` 已把它标成 `kind="retired"`。

本文件用 **TestClient 真发请求**（不是只测 service），理由是鉴权 / 路由命中 /
错误信封都在只有真请求才覆盖的层（memory 铁律 ㉕：只测 service 会漏掉鉴权）。

三条断言互相独立：
1. 未登录 ⇒ 401（退役端点不因 410 而变成匿名可达探针）；
2. 登录但无项目权限 ⇒ 403（项目门禁仍在）；
3. 有权限 ⇒ **410 + error_code**（而不是 200 / 422）。
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app


# ── 依赖覆盖：不碰真库 / 不碰真实鉴权链 ─────────────────────────────────────
# 注意：不能 override `require_project_access(...)` 这类**依赖工厂**（每次返回新函数
# 对象、key 匹配不上 ⇒ override 静默失效，全部变 401 —— memory 铁律 ㉕ 坑①）。
# 这里只覆盖内层 `get_db` 与 `get_current_user`，让真实判定链（含工厂）跑起来
# 在「无权限」这一侧；有权限那一侧单独 override 工厂本身，见下。


def _client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def anon_client() -> TestClient:
    return _client()


def test_retired_endpoint_requires_auth(anon_client: TestClient) -> None:
    """未登录访问退役端点 ⇒ 401，而不是 410。

    🔴 这条是防止「改成 410 时顺手摘掉鉴权依赖」——
    退役端点若匿名可达，它就变成一条不需要任何身份的探测口。
    """
    resp = anon_client.post(
        f"/api/projects/{uuid.uuid4()}/account-chart/import",
        files={"file": ("x.xlsx", b"not-a-real-xlsx", "application/octet-stream")},
    )
    assert resp.status_code == 401, f"期望 401（未登录），实得 {resp.status_code}: {resp.text[:200]}"


def test_retired_endpoint_is_registered_as_post_not_removed(anon_client: TestClient) -> None:
    """路径仍然挂着（不是被删掉），且方法仍是 POST —— 否则前端会拿到 404/405 而不是明确的 410。"""
    from app.services.ledger_import_entrypoints import (
        LEDGER_IMPORT_ENTRYPOINTS,
        _normalize_path,
    )

    target = "/api/projects/{project_id}/account-chart/import"
    entry = next(
        (e for e in LEDGER_IMPORT_ENTRYPOINTS if e.path == target), None
    )
    assert entry is not None and entry.kind == "retired"

    # 真实 app 里确实有这条 POST
    norm_target = _normalize_path(target)
    found = [
        r
        for r in app.routes
        if _normalize_path(getattr(r, "path", "") or "") == norm_target
        and "POST" in (getattr(r, "methods", set()) or set())
    ]
    assert found, "403/410 的前提是路由仍然挂着；404 说明路径被删了"


def test_retired_endpoint_returns_410_with_error_code() -> None:
    """有权限时的行为用 **AST** 判定：函数体第一条有效语句就是 raise HTTPException(410)。

    🔴 不用文本 `in` 匹配：`import_client_chart` 的 docstring 里写着
    「原先真的执行 `run_account_chart_import`」，文本判据会被自己的说明骗过
    （memory 铁律 ㉖：注释 / docstring 正反两向都会骗过文本扫描器）。
    """
    import ast
    import inspect
    import textwrap

    from app.routers.account_chart import import_client_chart

    src = textwrap.dedent(inspect.getsource(import_client_chart))
    tree = ast.parse(src)
    func = next(
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    )
    body = [n for n in func.body if not isinstance(n, ast.Expr)]  # 跳过 docstring
    assert body, "端点函数体不得为空"
    first = body[0]
    assert isinstance(first, ast.Raise), f"第一条语句必须是 raise，实得 {type(first).__name__}"
    call = first.exc
    assert isinstance(call, ast.Call)
    status = {kw.arg: kw.value for kw in call.keywords}.get("status_code")
    assert isinstance(status, ast.Constant) and status.value == 410

    # 反向（AST）：函数体里不得再出现对导入实现的**调用**
    called_names: set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            fn = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if fn:
                called_names.add(fn)
    assert "run_account_chart_import" not in called_names, (
        "退役端点不得再调用 run_account_chart_import（会真的写库）"
    )