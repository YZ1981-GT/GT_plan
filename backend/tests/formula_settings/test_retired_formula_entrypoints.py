"""名不副实的公式入口如实化（spec formula-management-repair-closure R3.2 / R3.3）。

- 旧 Excel 公式导入：``_import_formulas`` 调用的 ``cell_formula_evaluator.save_formula_batch`` 从未存在 ⇒ 每次导入都整批
  失败（失败原因是 ImportError 原文）。下线为 410 并指向「公式包」；类型清单与模板下载照旧（枚举保留）。
- 自定义函数写接口（注册 / 注销）的 501 由 ``test_custom_dsl_coding.py`` 经 ``app.main`` 覆盖，这里只钉源码不再写注册表。
"""
from __future__ import annotations

import ast
import io
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.deps import get_current_user
from app.routers import import_templates
from tests._test_auth_helper import FakeAuthUser

APP_ROOT = Path(__file__).resolve().parents[2] / "app"


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    async def _no_db():
        yield object()  # 哨兵：已下线的类型若真去用会话会 AttributeError ⇒ 500，不会是 410

    async def _deny_permission(*_a, **_k):
        raise AssertionError("已下线的导入类型不应走到项目权限校验")

    monkeypatch.setattr("app.deps.assert_project_permission", _deny_permission)
    app = FastAPI()
    app.include_router(import_templates.router)
    app.dependency_overrides[get_current_user] = lambda: FakeAuthUser()
    app.dependency_overrides[get_db] = _no_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _xlsx() -> dict:
    return {"file": ("公式.xlsx", io.BytesIO(b"PK\x03\x04"), "application/vnd.ms-excel")}


@pytest.mark.parametrize("action", ["validate", "import"])
def test_formula_excel_import_is_gone_with_pointer_to_package(client, action):
    params = {"project_id": str(uuid.uuid4()), "year": 2025} if action == "import" else {}
    r = client.post(f"/api/import-templates/formula/{action}", files=_xlsx(), params=params)
    assert r.status_code == 410, r.text
    detail = r.json()["detail"]
    assert detail["error_code"] == "IMPORT_TYPE_RETIRED" and "公式包" in detail["message"]


def test_type_list_and_template_download_still_work(client):
    assert "formula" in {t["type"] for t in client.get("/api/import-templates/types").json()}
    assert client.get("/api/import-templates/formula/download").status_code == 200


def test_other_import_types_are_untouched(client):
    """只停公式：别的类型照常走上传校验（非 Excel 文件 400），不会被 410 波及。"""
    r = client.post("/api/import-templates/staff/validate",
                    files={"file": ("人员.txt", io.BytesIO(b"x"), "text/plain")})
    assert r.status_code == 400 and "xlsx" in r.json()["detail"]


def test_ghost_batch_import_is_removed_from_source():
    """调用不存在函数的导入实现已删：模块里不再引用 save_formula_batch，也不再有 _import_formulas。"""
    tree = ast.parse((APP_ROOT / "routers" / "import_templates.py").read_text(encoding="utf-8"))
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
    defined = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert "save_formula_batch" not in imported and "_import_formulas" not in defined


def test_custom_function_write_endpoints_never_touch_registry():
    """注册 / 注销端点体内只抛 501：不调用服务层写函数（AST，注释与文档字符串不算）。"""
    tree = ast.parse((APP_ROOT / "routers" / "formula.py").read_text(encoding="utf-8"))
    bodies = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)
              and n.name in {"register_custom_function", "unregister_custom_function"}}
    assert set(bodies) == {"register_custom_function", "unregister_custom_function"}
    for name, fn in bodies.items():
        called = {getattr(c.func, "attr", getattr(c.func, "id", None)) for c in ast.walk(fn) if isinstance(c, ast.Call)}
        assert not called & {"register_custom_function", "unregister_custom_function"}, name
        assert any(isinstance(s, ast.Raise) for s in fn.body), name
