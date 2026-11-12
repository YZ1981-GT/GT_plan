"""差额表三端点的 query/body 项目范围一致性测试。

覆盖 spec consol-group-code-entry-consistency 任务 7.1 / R5：
路由依赖先按 query ``project_id`` 做项目权限与 RLS 门禁，函数体再拒绝
请求体项目不一致的请求，并只把已校验的 query 项目传给 service。
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.routers.consol_worksheet import (
    PivotRequest,
    RecalcRequest,
    TemplateCreateRequest,
    create_template,
    pivot_query,
    recalc_worksheet,
    router,
)


DB = object()
USER = object()
EXPECTED_DETAIL = "请求体项目与校验项目不一致"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("route", "body_factory", "service_module", "service_name"),
    [
        (
            recalc_worksheet,
            lambda project_id: RecalcRequest(project_id=project_id, year=2025),
            "app.services.consol_worksheet_engine",
            "recalc_full",
        ),
        (
            pivot_query,
            lambda project_id: PivotRequest(project_id=project_id, year=2025),
            "app.services.consol_pivot_service",
            "execute_query",
        ),
        (
            create_template,
            lambda project_id: TemplateCreateRequest(project_id=project_id, name="测试模板"),
            "app.services.consol_pivot_service",
            "save_template",
        ),
    ],
)
async def test_mismatched_body_project_is_rejected_before_service(
    monkeypatch: pytest.MonkeyPatch,
    route,
    body_factory,
    service_module: str,
    service_name: str,
):
    """项目权限校验的 query 项目不能被请求体项目替换。"""
    checked_project = uuid4()
    other_project = uuid4()
    service = __import__(service_module, fromlist=[service_name])
    mocked_service = AsyncMock()
    monkeypatch.setattr(service, service_name, mocked_service)

    with pytest.raises(HTTPException) as exc_info:
        await route(
            body=body_factory(other_project),
            project_id=checked_project,
            db=DB,
            current_user=USER,
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == EXPECTED_DETAIL
    mocked_service.assert_not_awaited()


@pytest.mark.asyncio
async def test_recalc_uses_checked_query_project(monkeypatch: pytest.MonkeyPatch):
    """重算 service 收到 query 中已通过权限校验的项目。"""
    from app.services import consol_worksheet_engine

    project_id = uuid4()
    mocked_recalc = AsyncMock(return_value={"rows_written": 0})
    monkeypatch.setattr(consol_worksheet_engine, "recalc_full", mocked_recalc)

    result = await recalc_worksheet(
        body=RecalcRequest(project_id=project_id, year=2025),
        project_id=project_id,
        db=DB,
        current_user=USER,
    )

    assert result == {"message": "重算完成", "rows_written": 0}
    assert mocked_recalc.await_args.args[:3] == (DB, project_id, 2025)


@pytest.mark.asyncio
async def test_pivot_uses_checked_query_project(monkeypatch: pytest.MonkeyPatch):
    """透视查询 service 收到 query 中已通过权限校验的项目。"""
    from app.services import consol_pivot_service

    project_id = uuid4()
    mocked_query = AsyncMock(return_value={"rows": []})
    monkeypatch.setattr(consol_pivot_service, "execute_query", mocked_query)

    body = PivotRequest(project_id=project_id, year=2025, filters={"account_codes": ["1001"]})
    result = await pivot_query(body=body, project_id=project_id, db=DB, current_user=USER)

    assert result == {"rows": []}
    assert mocked_query.await_args.args[:3] == (DB, project_id, 2025)


@pytest.mark.asyncio
async def test_create_template_uses_checked_query_project(monkeypatch: pytest.MonkeyPatch):
    """模板保存 service 收到 query 中已通过权限校验的项目。"""
    from app.services import consol_pivot_service

    project_id = uuid4()
    mocked_save = AsyncMock(return_value={"id": "template-1"})
    monkeypatch.setattr(consol_pivot_service, "save_template", mocked_save)

    result = await create_template(
        body=TemplateCreateRequest(project_id=project_id, name="测试模板"),
        project_id=project_id,
        db=DB,
        current_user=USER,
    )

    assert result == {"id": "template-1"}
    assert mocked_save.await_args.args[:3] == (DB, project_id, "测试模板")


def test_worksheet_write_routes_keep_project_access_dependencies():
    """三处端点仍保留项目级依赖，函数体校验不能替代鉴权。"""
    expected = {
        ("/recalc", "POST"): "edit",
        ("/pivot", "POST"): "readonly",
        ("/pivot/templates", "POST"): "edit",
    }

    for (path, method), level in expected.items():
        route = next(
            route for route in router.routes
            if route.path == f"/api/consolidation/worksheet{path}"
            and method in route.methods
        )
        dependency_callables = [item.call for item in route.dependant.dependencies]
        dependency = next(
            callable_ for callable_ in dependency_callables
            if getattr(callable_, "__name__", "") == "dependency"
        )
        assert inspect.getclosurevars(dependency).nonlocals["min_permission"] == level
