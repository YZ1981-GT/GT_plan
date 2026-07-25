"""audit-checks 全端点权限矩阵契约测试（audit-check-review-gate-hardening Task 5.4 / Property 12）。

锁定 `backend/app/routers/audit_check.py` 每个端点绑定的 `require_project_access` 权限档，
**不放宽既有授权**（Req10.1 权限零回归）。任何未来改动误放宽某端点权限（如 export 降为
无鉴权/更低档、signoff-POST 从 review 降为 edit/readonly、写端点从 edit 降为 readonly）
都会让本契约测试失败。

设计矩阵（design §3 / Property 12）：

| 端点                                                           | 方法 | 权限档   | 语义       |
|----------------------------------------------------------------|------|----------|------------|
| /api/projects/{pid}/audit-checks/summary                       | GET  | readonly | 项目只读   |
| /api/projects/{pid}/audit-checks/signoff                       | GET  | readonly | 读最近签认 |
| /api/projects/{pid}/audit-checks/recompute                     | POST | edit     | 编制权     |
| /api/projects/{pid}/workpapers/{wp_id}/audit-checks/report     | POST | edit     | 编制权     |
| /api/projects/{pid}/audit-checks/export                        | POST | readonly | 导出取数   |
| /api/projects/{pid}/audit-checks/signoff                       | POST | review   | 复核权     |

`require_project_access(level)` 是依赖工厂，返回捕获 `min_permission` 的闭包 dependency；
`user_level < required_level → 403`（即 level 是"至少需要该档"的下限门槛，非精确档）。
`PERMISSION_HIERARCHY = {"edit": 3, "review": 2, "readonly": 1}` → readonly < review < edit。

两层锁定（互为冗余，防单一手段失效导致假绿）：
1. **route 依赖内省**：遍历 `router.routes`，递归 `route.dependant` 找到 require_project_access
   闭包，从其 `__closure__` 提取 `min_permission` 实参 → 反映 FastAPI 运行时真实鉴权行为。
2. **源码正则**：对每个端点函数 `inspect.getsource` 抓 `require_project_access("X")` 实参 →
   直接锁定端点声明，可读锚点，且抓"完全无鉴权依赖"的裸端点。
"""

from __future__ import annotations

import inspect
import re

import pytest

from app.deps import PERMISSION_HIERARCHY
from app.routers import audit_check
from app.routers.audit_check import router as audit_check_router


# ═══════════════════════════════════════════
# 期望权限矩阵（单一真源，全部 6 个 (方法, 路径) → level 组合）
# ═══════════════════════════════════════════

# (method, path, expected_level, endpoint_function_name)
EXPECTED_MATRIX: list[tuple[str, str, str, str]] = [
    ("GET", "/api/projects/{project_id}/audit-checks/summary",
     "readonly", "get_audit_checks_summary"),
    ("GET", "/api/projects/{project_id}/audit-checks/signoff",
     "readonly", "get_latest_audit_check_signoff"),
    ("POST", "/api/projects/{project_id}/audit-checks/recompute",
     "edit", "recompute_audit_checks"),
    ("POST", "/api/projects/{project_id}/workpapers/{wp_id}/audit-checks/report",
     "edit", "report_audit_checks"),
    ("POST", "/api/projects/{project_id}/audit-checks/export",
     "readonly", "export_audit_checks"),
    ("POST", "/api/projects/{project_id}/audit-checks/signoff",
     "review", "create_audit_check_signoff"),
]


# ═══════════════════════════════════════════
# route 依赖内省工具
# ═══════════════════════════════════════════

def _walk_dependant(dep):
    """递归遍历 FastAPI Dependant 及其全部 sub-dependencies。"""
    yield dep
    for sub in getattr(dep, "dependencies", []) or []:
        yield from _walk_dependant(sub)


def _extract_level_from_call(call) -> str | None:
    """若 call 是 require_project_access 返回的闭包，从 __closure__ 提取 min_permission。"""
    if call is None:
        return None
    qualname = getattr(call, "__qualname__", "")
    if "require_project_access.<locals>" not in qualname:
        return None
    code = getattr(call, "__code__", None)
    closure = getattr(call, "__closure__", None)
    if code is None or closure is None:
        return None
    for name, cell in zip(code.co_freevars, closure):
        if name == "min_permission":
            return cell.cell_contents
    return None


def _route_permission_levels(route) -> list[str]:
    """内省单条 route，返回其绑定的所有 require_project_access level（正常应恰好 1 个）。"""
    dependant = getattr(route, "dependant", None)
    if dependant is None:
        return []
    levels: list[str] = []
    for dep in _walk_dependant(dependant):
        level = _extract_level_from_call(getattr(dep, "call", None))
        if level is not None:
            levels.append(level)
    return levels


def _find_route(method: str, path: str):
    """在 audit_check_router 中按 (method, path) 精确定位 route。"""
    for route in audit_check_router.routes:
        methods = getattr(route, "methods", None) or set()
        if getattr(route, "path", None) == path and method in methods:
            return route
    return None


# ═══════════════════════════════════════════
# 源码正则工具（第二层锁定）
# ═══════════════════════════════════════════

# 仅匹配 `Depends(require_project_access("X"))` 依赖注入声明形式，
# 不匹配 docstring/注释里裸提及的 `require_project_access("X")`（无 Depends 包裹）。
_REQUIRE_RE = re.compile(
    r'Depends\(\s*require_project_access\(\s*["\'](\w+)["\']\s*\)'
)


def _source_levels_for_endpoint(fn_name: str) -> list[str]:
    """对端点函数源码抓所有 Depends(require_project_access("X")) 实参（签名默认值）。"""
    fn = getattr(audit_check, fn_name)
    src = inspect.getsource(fn)
    return _REQUIRE_RE.findall(src)


# ═══════════════════════════════════════════
# 前提：档位语义锁定（level 是"至少需要该档"的下限门槛）
# ═══════════════════════════════════════════

def test_permission_hierarchy_semantics():
    """PERMISSION_HIERARCHY 档位定义与语义前提（readonly < review < edit）。

    锁定本契约赖以成立的档位排序：require_project_access(level) 用
    `user_level < required_level → 403`，level 越高门槛越严。若档位定义漂移，
    下方"不放宽"断言的语义基础也会改变，故先锁定。
    """
    assert PERMISSION_HIERARCHY == {"edit": 3, "review": 2, "readonly": 1}
    assert (
        PERMISSION_HIERARCHY["readonly"]
        < PERMISSION_HIERARCHY["review"]
        < PERMISSION_HIERARCHY["edit"]
    ), "档位排序须为 readonly < review < edit"


# ═══════════════════════════════════════════
# 主断言：全部 6 个 (方法, 路径, level) 组合（内省 + 源码双层）
# ═══════════════════════════════════════════

@pytest.mark.parametrize(
    "method,path,expected_level,fn_name",
    EXPECTED_MATRIX,
    ids=[f"{m}:{p.rsplit('/', 1)[-1]}={lv}" for m, p, lv, _ in EXPECTED_MATRIX],
)
def test_endpoint_permission_level_via_route_introspection(
    method, path, expected_level, fn_name
):
    """内省 route 依赖：每个端点绑定的 require_project_access level 与矩阵一致（运行时行为）。"""
    route = _find_route(method, path)
    assert route is not None, f"未找到 route {method} {path}（端点丢失或路径/方法变更）"

    levels = _route_permission_levels(route)
    assert levels, (
        f"{method} {path} 未绑定任何 require_project_access 依赖 —— 端点无鉴权（禁止裸露）"
    )
    assert len(levels) == 1, (
        f"{method} {path} 绑定了多个权限依赖 {levels}，应恰好 1 个"
    )
    assert levels[0] == expected_level, (
        f"{method} {path} 权限档为 {levels[0]!r}，矩阵要求 {expected_level!r}（不放宽授权）"
    )


@pytest.mark.parametrize(
    "method,path,expected_level,fn_name",
    EXPECTED_MATRIX,
    ids=[f"{fn}={lv}" for _, _, lv, fn in EXPECTED_MATRIX],
)
def test_endpoint_permission_level_via_source(
    method, path, expected_level, fn_name
):
    """源码正则：每个端点函数声明的 require_project_access("X") 与矩阵一致（可读锚点）。"""
    levels = _source_levels_for_endpoint(fn_name)
    assert levels, (
        f"端点 {fn_name} 源码未出现 require_project_access(...) —— 声明缺鉴权"
    )
    assert len(levels) == 1, (
        f"端点 {fn_name} 出现多个 require_project_access {levels}，应恰好 1 个"
    )
    assert levels[0] == expected_level, (
        f"端点 {fn_name} 声明权限档 {levels[0]!r}，矩阵要求 {expected_level!r}（不放宽授权）"
    )


# ═══════════════════════════════════════════
# 不放宽授权的定向断言（Req10.1 权限零回归）
# ═══════════════════════════════════════════

def test_readonly_endpoints_not_relaxed():
    """summary/signoff-GET/export 必须恰为 readonly —— 尤其 export 不得无鉴权/更低档。

    readonly 已是最低有效档：断言这三个读/导出端点均绑定 require_project_access("readonly")
    （既非缺失鉴权、也非误升到 edit/review 破坏只读语义）。
    """
    readonly_targets = [
        ("GET", "/api/projects/{project_id}/audit-checks/summary"),
        ("GET", "/api/projects/{project_id}/audit-checks/signoff"),
        ("POST", "/api/projects/{project_id}/audit-checks/export"),
    ]
    for method, path in readonly_targets:
        route = _find_route(method, path)
        assert route is not None, f"{method} {path} route 丢失"
        levels = _route_permission_levels(route)
        assert levels == ["readonly"], (
            f"{method} {path} 应恰绑 readonly，实为 {levels}（export 尤其不得放宽为无鉴权/更低）"
        )


def test_write_endpoints_require_edit():
    """recompute/report 写动作必须为 edit（不得降级为 readonly/review）。"""
    edit_targets = [
        ("POST", "/api/projects/{project_id}/audit-checks/recompute"),
        ("POST", "/api/projects/{project_id}/workpapers/{wp_id}/audit-checks/report"),
    ]
    for method, path in edit_targets:
        route = _find_route(method, path)
        assert route is not None, f"{method} {path} route 丢失"
        levels = _route_permission_levels(route)
        assert levels == ["edit"], (
            f"{method} {path} 写动作应绑 edit，实为 {levels}（不得降级放宽）"
        )


def test_signoff_post_requires_review():
    """signoff-POST 复核动作必须为 review（不得降级为 edit/readonly）。

    review(2) 低于 edit(3) 但语义是"至少复核权"——复核角色（review）与编制角色（edit）
    均可签认，符合"复核最后一次检查"的语义；关键是不得降到 readonly（只读者不能签认）。
    """
    route = _find_route("POST", "/api/projects/{project_id}/audit-checks/signoff")
    assert route is not None, "signoff POST route 丢失"
    levels = _route_permission_levels(route)
    assert levels == ["review"], (
        f"signoff-POST 应绑 review，实为 {levels}（复核动作，不得降为 readonly/edit）"
    )


# ═══════════════════════════════════════════
# 完整性：所有 audit-check 端点无一裸露（无鉴权）
# ═══════════════════════════════════════════

def test_no_audit_check_endpoint_without_permission_guard():
    """audit_check_router 每条业务 route 都必须绑定恰好 1 个 require_project_access 依赖。

    防未来新增端点忘加权限守卫（裸露）。以内省 + 期望矩阵覆盖数交叉校验。
    """
    business_routes = [
        r for r in audit_check_router.routes
        if getattr(r, "path", "").startswith("/api/projects/")
    ]
    assert business_routes, "audit_check_router 未发现业务 route（导入/注册异常）"

    for route in business_routes:
        methods = sorted(getattr(route, "methods", set()) or set())
        levels = _route_permission_levels(route)
        assert len(levels) == 1, (
            f"{methods} {route.path} 权限依赖数为 {len(levels)}（{levels}），"
            f"应恰好 1 个（裸露端点或重复守卫）"
        )
        assert levels[0] in PERMISSION_HIERARCHY, (
            f"{methods} {route.path} 权限档 {levels[0]!r} 不在 PERMISSION_HIERARCHY 中"
        )

    # (method, path) 覆盖数应与期望矩阵一致（新增未登记端点 → 提醒补矩阵）
    introspected = {
        (m, getattr(r, "path", ""))
        for r in business_routes
        for m in (getattr(r, "methods", set()) or set())
    }
    expected = {(m, p) for m, p, _, _ in EXPECTED_MATRIX}
    assert introspected == expected, (
        f"audit-check 端点集合与期望矩阵不一致：\n"
        f"  多出（未登记权限矩阵，需补契约）: {introspected - expected}\n"
        f"  缺失（端点被删/路径变更）: {expected - introspected}"
    )
