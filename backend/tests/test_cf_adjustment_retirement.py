"""现金流核查旧自动建分录入口退役契约。"""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from app import deps
from app.routers import cf_verification as cf_module
from app.services.cash_flow_verification_service import CashFlowVerificationService

PID = "123e4567-e89b-12d3-a456-426614174000"


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """只挂生产 CF router，隔离与本端点无关的全应用注册和数据库。"""
    api = FastAPI()
    api.include_router(cf_module.router)
    user = SimpleNamespace(id="user-1", role="auditor")

    async def current_user():
        return user

    async def db_session():
        yield SimpleNamespace()

    async def allow_project_access(_db, _user, _project_id, _permission):
        return user

    api.dependency_overrides[deps.get_current_user] = current_user
    api.dependency_overrides[deps.get_db] = db_session
    monkeypatch.setattr(deps, "assert_project_permission", allow_project_access)
    return api


async def test_retired_create_adjustment_returns_410_for_both_difference_signs(app: FastAPI):
    """差异正负不再触发任何自动借贷推断，旧请求统一得到迁移指引。"""
    path = f"/api/projects/{PID}/cf-verification/2025/create-adjustment"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for difference in (125.5, -125.5):
            response = await client.post(
                path,
                json={
                    "item_code": "CFS-001",
                    "difference": difference,
                    "description": "现金流核查差异",
                },
            )
            assert response.status_code == 410, response.text
            detail = response.json()["detail"]
            assert detail["error_code"] == "CF_ADJUSTMENT_CREATE_RETIRED"
            assert "手工选择完整借贷科目和方向后保存草稿" in detail["message"]
            assert detail["replacement"] == f"POST /api/projects/{PID}/adjustments"


def test_retired_handler_cannot_touch_request_body_or_database():
    """墓碑 handler 只有 raise，旧载荷即使带差异金额也没有写库路径。"""
    source = Path(cf_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    endpoint = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "create_cf_adjustment"
    )
    body = endpoint.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    assert len(body) == 1 and isinstance(body[0], ast.Raise)
    params = {arg.arg for arg in (*endpoint.args.args, *endpoint.args.kwonlyargs)}
    assert "body" not in params
    assert "db" not in params


def test_obsolete_cf_adjustment_service_method_is_not_exposed():
    assert not hasattr(CashFlowVerificationService, "create_cf_adjustment_from_diff")
    source = Path(__file__).resolve().parents[1] / "app/services/cash_flow_verification_service.py"
    assert "create_cf_adjustment_from_diff" not in source.read_text(encoding="utf-8")
