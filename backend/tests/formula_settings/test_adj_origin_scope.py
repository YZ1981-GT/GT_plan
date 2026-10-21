"""ADJ 口径守卫：底稿路径不排 origin，报表路径排 workpaper（spec formula-execution-path-convergence T13）。

两条路径的 ADJ 取数口径刻意不同：
- 底稿预填充：``adj_exclude_origins=frozenset()``（不排 origin，审计师看全部调整）
- 报表生成：``adj_exclude_origins=frozenset({"workpaper"})``（排 workpaper，防双计）

本守卫断言两条路径的调用传参，防止无意中统一成同一个口径。
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "app"


def _find_preload_calls(source: str) -> list[dict]:
    """在源码中找到 preload(...) 调用，提取 adj_exclude_origins 参数值。"""
    tree = ast.parse(source)
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            # preload(...) 或 await preload(...)
            name = ""
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name != "preload":
                continue
            for kw in node.keywords:
                if kw.arg == "adj_exclude_origins":
                    # 解析字面值
                    try:
                        val = ast.literal_eval(kw.value)
                    except (ValueError, TypeError):
                        # frozenset() 是 Call 节点，不是 literal；用 ast.unparse 判断
                        val = ast.unparse(kw.value)
                    calls.append({"value": val, "lineno": node.lineno})
    return calls


def test_prefill_engine_uses_empty_exclude():
    """底稿预填充路径的 preload 调用 adj_exclude_origins=frozenset()。"""
    source = (APP / "services" / "prefill_engine.py").read_text(encoding="utf-8")
    calls = _find_preload_calls(source)
    assert calls, "prefill_engine.py 中没找到 preload() 调用"
    for call in calls:
        val = call["value"]
        ok = val == frozenset() or (isinstance(val, str) and "frozenset()" in val)
        assert ok, (
            f"底稿路径 adj_exclude_origins 应为 frozenset()，实为 {val} (line {call['lineno']})"
        )


def test_report_engine_would_use_workpaper_exclude():
    """报表路径（evaluate_formula_result）的 adj_data 排除 workpaper origin。

    report_engine 目前不走 preload（Phase 3 留独立 spec），但其 adj_net_batch 调用
    带 exclude_origins=frozenset({"workpaper"})。本守卫断言该参数存在。
    """
    source = (APP / "services" / "report_engine.py").read_text(encoding="utf-8")
    # 找 adj_net_batch 调用中的 exclude_origins 参数
    tree = ast.parse(source)
    found_workpaper_exclude = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "exclude_origins":
                    try:
                        val = ast.literal_eval(kw.value)
                        if isinstance(val, frozenset) and "workpaper" in val:
                            found_workpaper_exclude = True
                    except (ValueError, TypeError):
                        # 可能是 frozenset({"workpaper"}) 形式的 Call 节点
                        src = ast.unparse(kw.value)
                        if "workpaper" in src:
                            found_workpaper_exclude = True
    assert found_workpaper_exclude, (
        "report_engine.py 的 adj_net_batch 调用应含 exclude_origins 且包含 'workpaper'"
    )
