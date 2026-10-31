"""自定义函数注册、环检测与嵌套 fail-closed handler（ADR-FHIC-17，需求 14.1/14.2）。

注册与 handler 从 ``FormulaEngine`` 搬到本模块；``FormulaEngine`` 同名方法只转发。

- **注册**：名称 ``.upper()``、参数名去重校验、元数据存进程内表。
- **环检测**：用 :func:`~app.services.formula_management.function_support_matrix.called_function_names`
  建「自定义函数 → 引用函数名」有向图，DFS 检测自环 / 互环。
- **handler**：``ContextVar`` 记嵌套深度（上限 8）；内层 ``not ok`` ⇒
  ``FormulaEvalError(内层原因)``；参数个数 ≠ ``len(param_names)`` ⇒ ``FormulaEvalError``。
"""
from __future__ import annotations

from contextvars import ContextVar
from decimal import Decimal
from typing import Any

from app.services.formula_management.function_support_matrix import called_function_names

# 延迟导入以避免循环
_engine_mod = None  # type: ignore[assignment]

_MAX_NESTING = 8
_nesting_depth: ContextVar[int] = ContextVar("custom_func_nesting", default=0)

# ── 进程内自定义函数注册表 ──────────────────────────────────────
_custom_registry: dict[str, dict[str, Any]] = {}
"""name(大写) → {expression, description, param_names}"""


def _engine():
    """延迟取 formula_engine 模块级对象（避免循环导入）。"""
    global _engine_mod
    if _engine_mod is None:
        from app.services import formula_engine as _mod
        _engine_mod = _mod
    return _engine_mod


# ── 环检测 ─────────────────────────────────────────────────────

def _detect_cycle(name: str, expression: str) -> str | None:
    """注册 *name* 前检测自环 / 互环。

    建「自定义 → 引用函数名」图，从 *name* 出发 DFS；
    只沿已注册自定义函数的边走（内置函数不会形成环）。
    返回 ``None`` 无环，否则返回中文原因。
    """
    # 临时把 name 加入图
    refs = called_function_names(expression)
    graph: dict[str, list[str]] = {}
    for n, meta in _custom_registry.items():
        graph[n] = called_function_names(meta["expression"])
    graph[name] = refs

    # DFS
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {k: WHITE for k in graph}
    path: list[str] = []

    def dfs(u: str) -> str | None:
        color[u] = GRAY
        path.append(u)
        for v in graph.get(u, []):
            v_upper = v.upper()
            if v_upper not in graph:
                continue  # 内置函数，跳过
            if color.get(v_upper) == GRAY:
                # 找到环
                cycle_start = path.index(v_upper)
                cycle = path[cycle_start:] + [v_upper]
                if len(set(cycle)) == 1:
                    return f"自定义函数 {name} 不能引用自身"
                return f"自定义函数存在循环引用：{'→'.join(cycle)}"
            if color.get(v_upper) == WHITE:
                result = dfs(v_upper)
                if result:
                    return result
        path.pop()
        color[u] = BLACK
        return None

    return dfs(name)


# ── 注册 / 注销 / 查询 ────────────────────────────────────────

def register_custom_function(
    name: str,
    expression: str,
    description: str = "",
    param_names: tuple[str, ...] | list[str] = (),
) -> dict:
    """注册自定义函数（ADR-FHIC-17）。

    Raises:
        ValueError: 名称为空、与内置冲突、参数名重复、表达式不合法、存在循环引用。
    """
    if not name or not name.strip():
        raise ValueError("函数名不能为空")

    name = name.strip().upper()
    eng = _engine()

    # 内置冲突检查
    builtin_names = eng._REGISTRY.known_function_names() - set(_custom_registry.keys())
    if name in builtin_names:
        raise ValueError(f"内置函数 {name} 不可覆盖")

    # 参数名去重校验
    pnames = list(param_names)
    if len(pnames) != len(set(pnames)):
        raise ValueError(f"参数名存在重复：{pnames}")

    # 表达式校验
    expr = expression or ""
    if expr and not eng._validate_custom_expression(expr):
        raise ValueError(f"表达式语法不合法: {expr}")

    # 环检测
    cycle_reason = _detect_cycle(name, expr)
    if cycle_reason:
        raise ValueError(cycle_reason)

    # 存入进程内表
    _custom_registry[name] = {
        "expression": expr,
        "description": description,
        "param_names": list(pnames),
    }

    # 构造 handler 并注册到 _REGISTRY
    def _handler(args: list[Any], ctx: "eng.FormulaContext", trace: list[str]) -> Decimal:
        """自定义函数 handler（ADR-FHIC-17）：嵌套深度限制 + 参数个数校验 + 内层 fail-closed。"""
        # 嵌套深度
        depth = _nesting_depth.get(0)
        if depth >= _MAX_NESTING:
            raise eng.FormulaEvalError(f"自定义函数 {name} 嵌套深度超过上限 {_MAX_NESTING}")

        # 参数个数校验
        expected = len(pnames)
        if expected > 0 and len(args) != expected:
            raise eng.FormulaEvalError(
                f"{name}() 参数个数不符：需要 {expected} 个参数，实际 {len(args)} 个"
            )

        token = _nesting_depth.set(depth + 1)
        try:
            result = eng.execute(expr, ctx)
            if not result.ok:
                reason = result.errors[0] if result.errors else f"{name}() 内层求值失败"
                raise eng.FormulaEvalError(reason)
            trace.append(f"{name}(...) = {result.value} (custom)")
            return result.value
        finally:
            _nesting_depth.reset(token)

    eng._REGISTRY.register(
        name, _handler, description=description, syntax="", category="自定义",
    )
    return {"registered": True, "name": name}


def unregister_custom_function(name: str) -> bool:
    """注销自定义函数。"""
    name_upper = name.strip().upper() if name else name
    removed = _custom_registry.pop(name_upper, None) is not None
    if removed:
        eng = _engine()
        eng._REGISTRY.unregister(name_upper)
    return removed


def list_custom_functions() -> list[dict]:
    """列出自定义函数。"""
    return [{"name": k, **v} for k, v in _custom_registry.items()]


def get_custom_registry() -> dict[str, dict[str, Any]]:
    """返回进程内自定义函数注册表（只读引用，供守卫使用）。"""
    return _custom_registry
