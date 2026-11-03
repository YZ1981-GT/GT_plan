"""``confirmation_project_gate`` 记作项目级鉴权令牌的前提（可伪证；spec attachment-security-baseline 需求 2.1）。

令牌登记在 tests/test_project_endpoint_authorization_baseline.py 的 ``_PROJECT_LEVEL_TOKENS``；判定口径
（``_auth_names_in_node`` / ``_router_vars``）直接复用该文件的实现，不另写一份。
"""
from __future__ import annotations

import ast

from tests.test_project_endpoint_authorization_baseline import (
    _PROJECT_LEVEL_TOKENS,
    _ROOT,
    _ROUTERS,
    _auth_names_in_node,
    _router_vars,
)


def test_confirmation_project_gate_is_really_project_level():
    """① 只在 services/confirmation_scope_gate.py 定义一份，函数体真的 await ``assert_project_permission``、
       并按请求方法定级（``required_level``）、核对路径与请求体对象（``require_*``）；
    ② 路由里用到它必须是从该模块导入的那一个，且挂在 ``APIRouter(dependencies=[...])`` 上。
    """
    assert "confirmation_project_gate" in _PROJECT_LEVEL_TOKENS
    gate_src = (_ROOT / "backend/app/services/confirmation_scope_gate.py").read_text(encoding="utf-8")
    gate = next(n for n in ast.walk(ast.parse(gate_src))
                if isinstance(n, ast.AsyncFunctionDef) and n.name == "confirmation_project_gate")
    awaited = {
        (n.value.func.id if isinstance(n.value.func, ast.Name) else n.value.func.attr)
        for n in ast.walk(gate) if isinstance(n, ast.Await) and isinstance(n.value, ast.Call)
    }
    assert "assert_project_permission" in awaited, "函证门不再 await assert_project_permission"
    assert {"require_confirmations", "require_attachments", "require_link", "require_workpapers"} <= awaited, awaited
    assert "required_level" in _auth_names_in_node(gate), "函证门不再按请求方法定级"
    users = {}
    for f in sorted(_ROUTERS.rglob("*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8-sig", errors="replace"))
        if any(isinstance(n, ast.Name) and n.id == "confirmation_project_gate" for n in ast.walk(tree)):
            users[f.relative_to(_ROUTERS).as_posix()] = (
                any(isinstance(n, ast.ImportFrom) and n.module == "app.services.confirmation_scope_gate"
                    and any(a.name == "confirmation_project_gate" for a in n.names) for n in ast.walk(tree)),
                "confirmation_project_gate" in _router_vars(tree).get("router", ("", set()))[1],
            )
    assert users == {"confirmations.py": (True, True)}, users
