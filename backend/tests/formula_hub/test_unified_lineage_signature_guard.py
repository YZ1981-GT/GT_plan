"""UnifiedLineage wrapper 签名与响应 schema 守卫。

spec formula-hub-integrity-closure 任务 27；需求 9.1~9.3；ADR-FHIC-16；变异 #32。
"""
from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path

import pytest
from fastapi.routing import APIRoute

from app.routers.lineage import router
from app.schemas.unified_lineage import UnifiedLineageResponse
from app.services.report_trace_service import ReportTraceService
from app.services.unified_lineage_service import (
    _SOURCE_BY_OBJECT_TYPE,
    _trace_identifier,
    UnifiedLineageService,
)
from app.services.version_line_service import version_line_service
from app.services.wp_trace_service import trace_downstream, trace_upstream


def _calls(wrapper, callee_name: str) -> list[ast.Call]:
    tree = ast.parse(textwrap.dedent(inspect.getsource(wrapper)))
    return [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            isinstance(node.func, ast.Name) and node.func.id == callee_name
            or isinstance(node.func, ast.Attribute) and node.func.attr == callee_name
        )
    ]


def _assert_call_binds(wrapper, callee_name: str, callee) -> None:
    calls = _calls(wrapper, callee_name)
    assert len(calls) == 1, f"{wrapper.__qualname__} 应恰好调用一次 {callee_name}，实得 {len(calls)}"
    call = calls[0]
    assert not any(isinstance(arg, ast.Starred) for arg in call.args), "签名守卫不接受 *args"
    assert all(keyword.arg is not None for keyword in call.keywords), "签名守卫不接受 **kwargs"
    positional = [object() for _ in call.args]
    keywords = {keyword.arg: object() for keyword in call.keywords if keyword.arg is not None}
    try:
        inspect.signature(callee).bind(*positional, **keywords)
    except TypeError as exc:
        pytest.fail(
            f"{wrapper.__qualname__} 调用 {callee_name} 的实参不符合真实签名 "
            f"{inspect.signature(callee)}：{exc}",
            pytrace=False,
        )


@pytest.mark.parametrize(
    ("wrapper", "callee_name", "callee"),
    [
        (UnifiedLineageService._query_wp_upstream, "trace_upstream", trace_upstream),
        (UnifiedLineageService._query_wp_downstream, "trace_downstream", trace_downstream),
        (UnifiedLineageService._query_report_trace, "trace_section", ReportTraceService().trace_section),
        (UnifiedLineageService._query_version_line, "query_lineage", version_line_service.query_lineage),
    ],
    ids=["upstream", "downstream", "report", "version"],
)
def test_wrapper_call_arguments_bind_to_real_callee_signature(wrapper, callee_name, callee):
    """以真实函数的 ``inspect.signature`` 校验 wrapper 调用，不 patch 被调函数。"""
    _assert_call_binds(wrapper, callee_name, callee)


def test_source_and_identifier_mapping_is_explicit_and_excludes_empty_types():
    assert _SOURCE_BY_OBJECT_TYPE == {
        "wp_cell": "workpaper",
        "report_row": "report",
        "note_cell": "disclosure",
    }
    assert "tb_row" not in _SOURCE_BY_OBJECT_TYPE
    assert "adjustment" not in _SOURCE_BY_OBJECT_TYPE
    assert _trace_identifier("wp_cell", "D2!B5") == "D2"
    assert _trace_identifier("report_row", "BS-007") == "BS-007"
    assert _trace_identifier("note_cell", "五、1") == "五、1"


def test_lineage_route_exposes_partial_and_errors_response_schema():
    routes = [route for route in router.routes if isinstance(route, APIRoute) and route.path.endswith("/lineage")]
    assert len(routes) == 1
    assert routes[0].response_model is UnifiedLineageResponse
    assert {"partial", "errors"} <= set(UnifiedLineageResponse.model_fields)


def test_pg_contract_does_not_patch_wrapper_trace_callees():
    """需求 9.3：真 PG 合同必须执行生产 wrapper 与真实 trace 函数。"""
    path = Path(__file__).with_name("test_unified_lineage_contract_pg.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden_imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
        if alias.name in {"mock", "unittest.mock"}
    }
    patch_calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            isinstance(node.func, ast.Name) and node.func.id in {"patch", "patch.object"}
            or isinstance(node.func, ast.Attribute) and node.func.attr == "patch"
        )
    ]
    assert forbidden_imports == set()
    assert patch_calls == []
