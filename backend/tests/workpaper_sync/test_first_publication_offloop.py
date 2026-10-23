"""首版发布的整簿读文件 + 提取不在事件循环上（spec writeback-followup-issue-closure R9 / P11）。

`publish_first_generation` 是 async 函数，原先在事件循环上同步调 `_overlay_store_on_substrate_baseline`
（`adapter.extract` 整簿解析，D2 约 1 s）：单 worker 部署下首次打开在线编辑的这一段全平台无响应。
真库行为由 `test_projection_first_publication_pg.py` 覆盖（结果不变）；这里钉住接线：只经
`asyncio.to_thread` 调用、不再直接调用；以及被放进线程的函数确实不碰数据库会话。
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from app.services.workpaper_sync import projection_first_publication as F

_TREE = ast.parse(Path(F.__file__).read_text(encoding="utf-8"))
_TARGET = "_overlay_store_on_substrate_baseline"


def _function(name: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    return next(
        node for node in ast.walk(_TREE)
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name
    )


def _calls(fn: ast.AST) -> list[ast.Call]:
    return [node for node in ast.walk(fn) if isinstance(node, ast.Call)]


def _is_to_thread(call: ast.Call) -> bool:
    func = call.func
    return isinstance(func, ast.Attribute) and func.attr == "to_thread" and getattr(func.value, "id", "") == "asyncio"


def test_overlay_extraction_runs_in_a_worker_thread():
    publish = _function("publish_first_generation")
    direct = [c for c in _calls(publish) if getattr(c.func, "id", None) == _TARGET]
    assert not direct, f"第 {direct[0].lineno} 行在事件循环上直接调 {_TARGET}" if direct else ""
    threaded = [
        c for c in _calls(publish)
        if _is_to_thread(c) and c.args and getattr(c.args[0], "id", None) == _TARGET
    ]
    assert len(threaded) == 1, "整簿提取必须经 asyncio.to_thread 调用"


def test_threaded_function_touches_no_session():
    source = inspect.getsource(F._overlay_store_on_substrate_baseline)
    params = inspect.signature(F._overlay_store_on_substrate_baseline).parameters
    assert "session" not in params and "session" not in source, "放进工作线程的函数不得持有数据库会话"
