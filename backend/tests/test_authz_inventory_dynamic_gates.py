"""动态项目门禁的清册识别与生产结构守卫（residual R7）。"""
from __future__ import annotations

import ast
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "gen"))
from authz_inventory import gates, selfcheck  # noqa: E402


def _method_source(method: str) -> str:
    return textwrap.dedent(f'''
        from fastapi import APIRouter, Depends
        from app.services.confirmation_scope_gate import confirmation_project_gate
        router = APIRouter(dependencies=[Depends(confirmation_project_gate)])
        @router.{method.lower()}("/api/projects/{{project_id}}/confirmations")
        async def endpoint(project_id: str):
            return None
    ''')


def test_confirmation_router_gate_level_is_derived_from_http_method() -> None:
    expected = {"GET": "readonly", "HEAD": "readonly", "POST": "edit", "PUT": "edit", "PATCH": "edit", "DELETE": "edit"}
    for method, level in expected.items():
        result = selfcheck.recognize_source(_method_source(method), "endpoint")
        uses = [use for use in result.uses if use.name == "confirmation_project_gate"]
        assert len(uses) == 1
        assert (uses[0].level, uses[0].level_origin, uses[0].via) == (level, "method", "router")
        assert not [issue for issue in result.issues if issue.kind == gates.LEVEL_UNDETERMINED]


def test_method_level_has_fail_closed_default_and_requires_a_route_method() -> None:
    policy = gates.MethodLevel()
    assert policy.resolve("GET") == "readonly"
    assert policy.resolve("HEAD") == "readonly"
    assert policy.resolve("POST") == "edit"
    assert policy.resolve("OPTIONS") == "edit"
    assert policy.resolve(None) is None


def test_attachment_permission_is_registered_as_object_gate_with_caller_level() -> None:
    source = textwrap.dedent('''
        from fastapi import APIRouter
        from app.services.attachment_access import require_attachment_permission
        router = APIRouter()
        @router.get("/api/attachments/{attachment_id}")
        async def endpoint(db, user, attachment_id):
            return await require_attachment_permission(db, user, attachment_id, "readonly")
    ''')
    result = selfcheck.recognize_source(source, "endpoint")
    use = next(use for use in result.uses if use.name == "require_attachment_permission")
    assert (use.category, use.level, use.level_origin) == ("project_object", "readonly", "literal")
    assert not result.issues

    spec = gates.REGISTRY["require_attachment_permission"]
    assert spec.home == "app.services.attachment_access"
    production = (ROOT / "app/services/attachment_access.py").read_text(encoding="utf-8")
    tree = ast.parse(production)
    function = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
                    and node.name == "require_attachment_permission")
    assert "load_attachment" in {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
    call = next(node for node in ast.walk(function) if isinstance(node, ast.Call)
                and getattr(node.func, "id", None) == "assert_project_permission")
    assert ast.unparse(call.args[2]) == "att.project_id"
    assert ast.unparse(call.args[3]) == "min_permission"


def test_ocr_cached_and_write_paths_are_two_explicit_literal_gates() -> None:
    source = (ROOT / "app/routers/ocr_fields.py").read_text(encoding="utf-8")
    info = gates.analyze_module("backend/app/routers/ocr_fields.py", source)
    declared = next(route for route in info.declared_routes() if route.function == "extract_ocr_fields")
    result = gates.recognize_endpoint(info, declared)
    uses = [use for use in result.uses if use.name == "assert_project_permission"]
    assert {(use.level, use.conditional) for use in uses} == {("readonly", True), ("edit", True)}
    assert all(use.level_origin == "literal" for use in uses)
    assert not [issue for issue in result.issues if issue.kind == gates.LEVEL_UNDETERMINED]
