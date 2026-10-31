"""L1 内置函数名单、参数个数表与表达式结构预算（spec formula-hub-integrity-closure ADR-FHIC-01 / 02，需求 2.2、2.9、12.3）。

- :data:`BUILTIN_FUNCTION_NAMES`：L1 内核（``formula_engine._REGISTRY``）注册的全部**内置**函数名，字面量写死
  （= 实施时 HEAD 的 20 个注册键）。自定义函数注册后进 ``_REGISTRY`` 但不进本名单。
- :data:`ARITY`：内置函数 → ``(最少参数, 最多参数 | None = 不限)``，手工维护；键集合 == 名单（守卫
  ``tests/formula_hub/test_l1_failure_semantics.py::test_arity_keys``）。自定义函数的参数个数 = 注册时
  ``param_names`` 的长度（ADR-FHIC-17），不归本表管。
- 求值期（L1 ``_eval_func_node`` 与 ``safe_eval_expr``）只查下限，另查 ``IF`` 上限；写入期 validator 上下限都查
  （``arity_problem(..., full=True)``）。
- AST 预算：节点 > :data:`MAX_AST_NODES` 或深度 > :data:`MAX_AST_DEPTH` 在求值前报错（深度：根为 1，
  父 = 1 + 最深的子；``a+b+c`` 是左结合的链，深度 = 项数）。

下限依据 = 各 handler 与 ``formula_preloader`` 预载正则能取到数的写法：低于下限的写法预载层从不取数、
handler 把缺的参数当空串或默认值取，原先一律静默得 0（2026-10-27 现存公式探针：低于下限的只有说明文字与
``refs`` 引用描述，没有被求值的公式）。
"""
from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterable, Sequence
from typing import Any

#: L1 内置函数全集（字面量；实施时 = HEAD ``formula_engine._REGISTRY`` 的全部键）。
BUILTIN_FUNCTION_NAMES: frozenset[str] = frozenset({
    "TB", "SUM_TB", "PREV", "AUX", "NOTE", "WP", "ADJ",
    "ROW", "SUM_ROW", "REPORT",
    "ABS", "ROUND", "MAX", "MIN", "IF",
    "LEDGER", "LEDGER_DETAIL", "TB_AUX", "COUNT_LEDGER", "PLACEHOLDER",
})

#: 内置函数 → (最少参数, 最多参数 | None)。
ARITY: dict[str, tuple[int, int | None]] = {
    # 取数
    "TB": (1, 2),             # TB('科目'[,'列名'])，缺列名按上下文默认列
    "SUM_TB": (1, 2),         # SUM_TB('起~止'[,'列名'])
    "PREV": (2, 3),           # PREV('科目','列') / PREV('底稿','表','字段')；PREV(TB('科目','列')) 按内层计（call_argc）
    "AUX": (2, 4),            # AUX('科目','维度'[,'辅助项'],'列')：两参 / 三参 / 四参
    "NOTE": (2, 3),           # NOTE('章节','行'[,'列'])；预载正则至少两参
    "WP": (2, 3),             # WP('底稿','列名|单元格') / WP('底稿','表','锚点')
    "ADJ": (1, 2),            # ADJ('科目'[,'aje_net|rje_net'])
    # 引用
    "ROW": (1, 1),
    "SUM_ROW": (2, 2),
    "REPORT": (1, 2),         # REPORT('行次'[,'期间'])
    # 数学 / 逻辑
    "ABS": (1, 1),
    "ROUND": (1, 2),          # ROUND(值[,位数])，缺位数按 2
    "MAX": (2, None),
    "MIN": (2, None),
    "IF": (3, 3),
    # 底稿预填（formula_preloader：_LEDGER_RE / _LEDGER_DETAIL_RE / _TB_AUX_RE / _COUNT_LEDGER_RE）
    "LEDGER": (2, 3),         # LEDGER('科目','方向'[,'范围'])
    "LEDGER_DETAIL": (1, 3),  # LEDGER_DETAIL('科目'[,'期间'][,'金额条件'])
    "TB_AUX": (3, 3),         # TB_AUX('科目','维度','列名')：预载正则只认三参
    "COUNT_LEDGER": (1, 2),   # COUNT_LEDGER('科目'[,'范围'])
    "PLACEHOLDER": (0, 1),
}

#: 求值期也查上限的函数（其余函数多给的参数由 handler 忽略，写入期 validator 再拒）。
EVAL_UPPER_CHECKED: frozenset[str] = frozenset({"IF"})

MAX_AST_NODES = 2000
MAX_AST_DEPTH = 50


def call_argc(name: str, args: Sequence[Any]) -> int:
    """判参数个数用的实参个数：``PREV(TB('科目','列'))`` 按内层 TB 的实参计（与 ``_handle_prev`` 同口径）。"""
    if name == "PREV" and len(args) == 1 and getattr(args[0], "name", None) == "TB":
        return len(getattr(args[0], "args", ()))
    return len(args)


def arity_problem(name: str, argc: int, *, full: bool = False) -> str | None:
    """内置函数参数个数不符的中文原因；符合、或不是内置函数（自定义 / 未注册）⇒ ``None``。

    ``full=False``（求值期）：只查下限，另查 :data:`EVAL_UPPER_CHECKED` 的上限；``full=True``（写入期）：上下限都查。
    """
    bounds = ARITY.get(name)
    if bounds is None:
        return None
    low, high = bounds
    too_many = high is not None and argc > high and (full or name in EVAL_UPPER_CHECKED)
    if argc >= low and not too_many:
        return None
    if low == high:
        need = f"需要 {low} 个参数"
    elif high is None:
        need = f"至少需要 {low} 个参数"
    else:
        need = f"需要 {low}~{high} 个参数"
    return f"{name}() 参数个数不符：{need}，实际 {argc} 个"


def dataclass_children(node: Any) -> Iterable[Any]:
    """L1 AST 节点（dataclass，无 slots）的直接子节点：字段值本身或列表里的 dataclass 实例。"""
    for value in vars(node).values():
        for child in value if isinstance(value, list) else (value,):
            if dataclasses.is_dataclass(child) and not isinstance(child, type):
                yield child


def ast_budget_problem(root: Any, children: Callable[[Any], Iterable[Any]] = dataclass_children) -> str | None:
    """AST 节点数 > :data:`MAX_AST_NODES` 或深度 > :data:`MAX_AST_DEPTH` ⇒ 中文原因，否则 ``None``。

    显式栈遍历（不递归），超限即停；``children`` 默认按 L1 dataclass 节点取子节点，``safe_eval_expr`` 传
    ``ast.iter_child_nodes``（Python AST 多出 ``Load`` 等上下文节点，同一表达式的计数略大）。
    """
    nodes, stack = 0, [(root, 1)]
    while stack:
        node, depth = stack.pop()
        nodes += 1
        if nodes > MAX_AST_NODES:
            return f"表达式超出求值预算：AST 节点超过 {MAX_AST_NODES} 个"
        if depth > MAX_AST_DEPTH:
            return f"表达式超出求值预算：AST 深度超过 {MAX_AST_DEPTH} 层"
        stack.extend((child, depth + 1) for child in children(node))
    return None
