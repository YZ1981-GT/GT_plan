"""writer 清册的 SQL 变量绑定：``text(sql)`` 里的 ``sql`` 先在同一函数里赋了字面量。

清册的 ``_record_sql_text`` 原先只认 ``text("…")`` 的字面量实参。公式运行时的底稿适配器
（``WorkpaperMutationAdapter.restore_many``，此前还有 ``apply_many``）按列名分支把
``UPDATE checklist_responses …`` / ``INSERT INTO checklist_responses …`` 先赋给局部变量，再
``text(update_sql)`` 执行 ⇒ 写 ``checklist_responses.remark / conclusion`` 的路径在清册里看不见，
这两行被当成「只委派 parsed_data 的写入方」，2026-11-04 的裁决还据此把 lane 改错了。

这里收集函数自身语句里对同一名字的全部字符串赋值（分支各赋一次 ⇒ 都算），交给
``_record_sql_text`` 逐条判。只看函数自身的语句（嵌套函数归它自己的行）；只认赋值右侧本身就是
SQL 字面量（``_sql_literal`` 认得的常量 / f-string）的形态。参数、模块常量、运行时拼接与
``.format`` 不在此列：2026-11-04 现算全仓 ``backend/app`` 里 ``text()`` 的实参没有这几种写库形态。
"""
from __future__ import annotations

import ast
from collections.abc import Callable, Iterable


def sql_text_bindings(
    function: ast.AST,
    own_nodes: Callable[[ast.AST], Iterable[ast.AST]],
    literal_of: Callable[[ast.AST], str | None],
) -> dict[str, list[str]]:
    """``{局部变量名: [本函数里赋给该名字的每条 SQL 字面量]}``。"""
    bound: dict[str, list[str]] = {}
    for node in own_nodes(function):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
            continue
        literal = literal_of(node.value)
        if literal is None:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                bound.setdefault(target.id, []).append(literal)
    return bound
