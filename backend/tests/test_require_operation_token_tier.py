"""鉴权基线把 ``require_operation`` 记作项目级的前提可伪证（spec consol-autotree-residual-closure R3.3）。

``test_project_endpoint_authorization_baseline._PROJECT_LEVEL_TOKENS`` 里有 ``require_operation``：项目 id 在路径 / 查询参数里时，
它先挡已归档项目、权限矩阵放行后再对该项目 ``assert_project_permission``。此前它只看权限矩阵、不校成员，却一直被记作项目级。
这里按 AST 读 ``deps.require_operation`` 的 ``dependency``，三条前提任一不成立即红（docstring / 注释里提到不算，memory ㉖）。
项目在请求体里的端点它看不到项目，请求体维不认它（``test_project_endpoint_authz_body_carried``）。
"""
from __future__ import annotations

import ast
import pathlib

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[2]

#: 前提（事实键 → 不成立时的说明）
_REQUIRE_OPERATION_FACTS = {
    "project_id_param": "依赖不再从路径 / 查询参数取 project_id",
    "member_gate": "依赖不再对 project_id 调 assert_project_permission —— 退回只看权限矩阵、不校成员",
    "archive_guard": "依赖不再判已归档项目（_check_project_not_archived）",
}


def _require_operation_facts(src: str) -> dict[str, bool]:
    """按 AST 读 ``require_operation`` 工厂里的 ``dependency``。"""
    tree = ast.parse(src)
    factory = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "require_operation"), None)
    inner = next((n for n in ast.walk(factory) if isinstance(n, ast.AsyncFunctionDef) and n.name == "dependency"),
                 None) if factory is not None else None
    if inner is None:
        return dict.fromkeys(_REQUIRE_OPERATION_FACTS, False)
    calls = [n for n in ast.walk(inner) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    return {
        "project_id_param": any(a.arg == "project_id" for a in inner.args.args),
        "member_gate": any(c.func.id == "assert_project_permission" and len(c.args) >= 3
                           and isinstance(c.args[2], ast.Name) and c.args[2].id == "project_id" for c in calls),
        "archive_guard": any(c.func.id == "_check_project_not_archived" for c in calls),
    }


@pytest.mark.parametrize("fact", sorted(_REQUIRE_OPERATION_FACTS))
def test_require_operation_token_is_really_project_level(fact: str):
    src = (_ROOT / "backend/app/deps.py").read_text(encoding="utf-8")
    assert _require_operation_facts(src)[fact], _REQUIRE_OPERATION_FACTS[fact]


def test_require_operation_facts_can_fail():
    """反向自检：只看权限矩阵的旧实现两条判定都不成立（防事实判定恒真）。"""
    old = (
        "def require_operation(operation):\n"
        "    async def dependency(current_user=None, project_id=None, db=None):\n"
        "        '''矩阵放行后 assert_project_permission(db, current_user, project_id) 与 _check_project_not_archived'''\n"
        "        project_role = await _resolve_project_role(db, current_user.id, project_id)\n"
        "        if not can(current_user.role.value, project_role, operation):\n"
        "            raise HTTPException(status_code=403)\n"
        "        return current_user\n"
        "    return dependency\n"
    )
    facts = _require_operation_facts(old)
    assert facts == {"project_id_param": True, "member_gate": False, "archive_guard": False}


def test_baseline_still_counts_require_operation_as_project_level():
    """前提钉的是基线口径：基线的项目级 token 里确实有它（拿掉了这组前提就没有意义）。"""
    src = (_ROOT / "backend/tests/test_project_endpoint_authorization_baseline.py").read_text(encoding="utf-8")
    tokens = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "_PROJECT_LEVEL_TOKENS" for t in n.targets))
    assert "require_operation" in [e.value for e in tokens.value.elts if isinstance(e, ast.Constant)]
