"""tb_detail 止血：保存 tb_detail 不改任何 working_paper.prefill_stale（需求 15.4）。

验证 ``propagate_tb_detail`` 不写库、不改 prefill_stale：
1. 调用返回 ``{"skipped": "no_consumer"}``，不含 ``"marked"``。
2. AST 守卫：函数体不含 ``WorkingPaper`` / ``prefill_stale`` / ``update`` / ``commit``。
"""
from __future__ import annotations

import ast
import inspect
import uuid

import pytest

from app.services.formula_settings.propagation import propagate_tb_detail


@pytest.mark.asyncio
async def test_propagate_tb_detail_returns_no_consumer():
    """propagate_tb_detail 直接返回 skipped=no_consumer，不需要数据库。"""
    result = await propagate_tb_detail(uuid.uuid4(), 2025, ["1001", "1002"])
    assert result["skipped"] == "no_consumer"
    assert "marked" not in result
    assert result["slot_keys"] == ["1001", "1002"]


@pytest.mark.asyncio
async def test_propagate_tb_detail_no_year():
    """即使年度为 None，仍返回 skipped。"""
    result = await propagate_tb_detail(uuid.uuid4(), None, ["added:X1"])
    assert result["skipped"] == "no_consumer"


def test_propagate_tb_detail_body_has_no_write_operations():
    """AST 守卫：propagate_tb_detail 函数体不含任何写库操作。

    禁止的名字（Name / Attribute 末段）：
    - WorkingPaper（ORM 模型）
    - prefill_stale（列名）
    - update / commit（写入动词）
    - _factory / _is_frozen（旧写入路径辅助）
    """
    source = inspect.getsource(propagate_tb_detail)
    tree = ast.parse(source)
    # 取函数体（跳过装饰器）
    func_def = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef))

    forbidden = {"WorkingPaper", "prefill_stale", "update", "commit", "_factory", "_is_frozen"}
    found: list[str] = []
    for node in ast.walk(func_def):
        if isinstance(node, ast.Name) and node.id in forbidden:
            found.append(node.id)
        if isinstance(node, ast.Attribute) and node.attr in forbidden:
            found.append(node.attr)
    assert not found, f"propagate_tb_detail 函数体含禁止的名字：{found}"
