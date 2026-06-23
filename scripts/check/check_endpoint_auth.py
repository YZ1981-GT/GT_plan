"""CI lint: 检测写端点是否声明了授权依赖

扫描 backend/app/routers/*.py，对每个 @router.post/put/patch/delete 修饰函数
检查其参数中是否包含 require_operation / require_project_access / require_role。
未声明的端点输出 WARNING + 路径。

退出码：
- 0: 全部通过或仅 warning（非阻塞模式）

用法：
  python scripts/check/check_endpoint_auth.py [--strict]
  --strict: 有违规时 exit 1（阻塞 CI）
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# ─── 项目根目录 ─────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ROUTERS_DIR = _PROJECT_ROOT / "backend" / "app" / "routers"

# ─── 豁免端点（不需要授权的公共端点） ────────────────────────────────────────
_EXEMPT_ENDPOINTS = {
    # health / readiness
    "health",
    "healthz",
    "readiness",
    "ready",
    # auth
    "login",
    "register",
    "refresh_token",
    "logout",
    # SSE events
    "events",
    "event_stream",
    "sse_events",
    # webhook / callback
    "onlyoffice_callback",
    "webhook",
}

# ─── 写操作 HTTP 方法 ────────────────────────────────────────────────────────
_WRITE_METHODS = {"post", "put", "patch", "delete"}

# ─── 授权依赖关键字 ──────────────────────────────────────────────────────────
_AUTH_DEPENDS = {
    "require_operation",
    "require_project_access",
    "require_role",
    "get_current_user",
    "require_confirmation_token",
}


def _is_router_decorator(decorator: ast.expr) -> str | None:
    """判断装饰器是否为 router.post/put/patch/delete，返回方法名或 None。"""
    if isinstance(decorator, ast.Call):
        decorator = decorator.func
    if isinstance(decorator, ast.Attribute):
        method = decorator.attr.lower()
        if method in _WRITE_METHODS:
            # 检查是否是 router.xxx 或 xxx_router.xxx
            if isinstance(decorator.value, ast.Name):
                if "router" in decorator.value.id.lower():
                    return method
    return None


def _has_auth_depends(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """检查函数参数默认值中是否包含授权依赖。"""
    for arg in func_node.args.args + func_node.args.kwonlyargs:
        # 检查默认值
        pass

    # 检查所有参数的默认值（args + kwonlyargs 的 defaults 分布）
    all_defaults = func_node.args.defaults + func_node.args.kw_defaults
    for default in all_defaults:
        if default is None:
            continue
        source = ast.dump(default)
        for auth_dep in _AUTH_DEPENDS:
            if auth_dep in source:
                return True

    return False


def _is_exempt(func_name: str) -> bool:
    """是否为豁免函数。"""
    return func_name.lower() in _EXEMPT_ENDPOINTS


def scan_file(filepath: Path) -> list[dict]:
    """扫描单个文件，返回缺少授权声明的端点列表。"""
    violations = []
    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(filepath))
    except (SyntaxError, UnicodeDecodeError):
        return violations

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        # 跳过豁免端点
        if _is_exempt(node.name):
            continue

        # 检查是否有写操作装饰器
        http_method = None
        for decorator in node.decorator_list:
            method = _is_router_decorator(decorator)
            if method:
                http_method = method
                break

        if http_method is None:
            continue

        # 检查是否有授权依赖
        if not _has_auth_depends(node):
            violations.append({
                "file": str(filepath.relative_to(_PROJECT_ROOT)),
                "function": node.name,
                "method": http_method.upper(),
                "line": node.lineno,
            })

    return violations


def main() -> int:
    """主入口。"""
    strict = "--strict" in sys.argv

    if not _ROUTERS_DIR.exists():
        print(f"ERROR: 路由目录不存在: {_ROUTERS_DIR}")
        return 1

    all_violations: list[dict] = []

    for py_file in sorted(_ROUTERS_DIR.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        violations = scan_file(py_file)
        all_violations.extend(violations)

    if not all_violations:
        print("✅ 所有写端点均已声明授权依赖")
        return 0

    print(f"⚠️  检测到 {len(all_violations)} 个写端点缺少授权声明：\n")
    for v in all_violations:
        print(f"  WARNING: {v['file']}:{v['line']} {v['method']} {v['function']}")

    if strict:
        print(f"\n❌ --strict 模式：{len(all_violations)} 个违规，CI 失败")
        return 1

    print(f"\n⚠️  非阻塞模式：{len(all_violations)} 个 warning（后续达到覆盖率后切换为 fail）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
