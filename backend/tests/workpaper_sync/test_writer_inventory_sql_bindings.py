"""writer 清册：``text(<局部变量>)`` 执行的写库 SQL 必须进事实（2026-11-04 审计整改）。

清册的 ``_record_sql_text`` 原先只认 ``text("…")`` 的字面量实参。公式运行时的底稿适配器
``WorkpaperMutationAdapter.restore_many`` 按列名分支把 ``UPDATE checklist_responses …`` 先赋给局部
变量再 ``text(update_sql)`` ⇒ 它写 ``checklist_responses`` 的路径在清册里不存在，行被当成「只委派
parsed_data」，Task 74 的裁决也据此把 lane 改错了。修法在发现谓词里（``writer_inventory_sql_bindings``），
本文件钉住三件事：合成源码上的正反用例、真实行、全仓现算对账（同一盲区不得在别处复现）。
"""
from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
_GENERATOR_PATH = _BACKEND / "scripts" / "gen" / "generate_workpaper_writer_inventory.py"
_INVENTORY_PATH = _BACKEND / "data" / "workpaper_writer_inventory.json"
_APP = _BACKEND / "app"
_RESTORE_MANY = "app.services.formula_runtime.adapters.workpaper::WorkpaperMutationAdapter.restore_many"


@pytest.fixture(scope="module")
def generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sql_bindings_writer_inventory_generator", _GENERATOR_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _facts(generator: ModuleType, source: str, function_name: str) -> dict[str, Any]:
    for qualname, node in generator._iter_functions(ast.parse(source)):
        if qualname.rsplit(".", 1)[-1] == function_name:
            return generator._collect_facts(node).as_dict()
    raise AssertionError(f"合成源码里没有函数 {function_name}")


_BRANCH_BOUND = '''
from sqlalchemy import text

async def restore(session, storage_col, value):
    if storage_col == "conclusion":
        update_sql = (
            "UPDATE checklist_responses "
            "SET conclusion = :col_value, updated_at = :now "
            "WHERE wp_id = :wp_id AND item_id = :item_id"
        )
    else:
        update_sql = (
            "UPDATE checklist_responses "
            "SET remark = :col_value, updated_at = :now "
            "WHERE wp_id = :wp_id AND item_id = :item_id"
        )
    await session.execute(text(update_sql), {"col_value": value})
'''

_NOT_WRITES = '''
from sqlalchemy import text

async def read_only(session, sql_from_caller):
    probe_sql = "SELECT remark FROM checklist_responses WHERE wp_id = :wp_id"
    await session.execute(text(probe_sql))
    await session.execute(text(sql_from_caller))

    def nested():
        # 同名变量只在嵌套函数里赋了写库 SQL：它归嵌套函数自己的行，不得串到外层的 text(sql_from_caller)
        sql_from_caller = "UPDATE checklist_responses SET remark = :v WHERE wp_id = :w"
        return sql_from_caller

    return nested
'''

_LITERAL = '''
from sqlalchemy import text

async def save(session):
    await session.execute(text("UPDATE checklist_responses SET remark = :v WHERE wp_id = :w"))
'''


def test_branch_bound_sql_reaches_the_facts(generator: ModuleType) -> None:
    """两个分支各赋一次 ⇒ 两列都算（漏一个分支就漏一列内容写入）。"""
    columns = set(_facts(generator, _BRANCH_BOUND, "restore")["sql_update_columns"])
    assert {"checklist_responses.remark", "checklist_responses.conclusion"} <= columns, columns


def test_bindings_do_not_invent_writes(generator: ModuleType) -> None:
    """反向：SELECT 不是写入；参数传进来的 SQL 看不见内容，不臆造；嵌套函数的变量不串到外层。"""
    assert _facts(generator, _NOT_WRITES, "read_only")["sql_update_columns"] == []


def test_literal_argument_still_counts(generator: ModuleType) -> None:
    assert _facts(generator, _LITERAL, "save")["sql_update_columns"] == ["checklist_responses.remark"]


def test_restore_many_row_names_its_checklist_write() -> None:
    """真实行：undo 一半自己写 checklist_responses（变量绑定的 UPDATE），裁决回到 checklist lane。

    它同时直接调 ``write_cell_to_parsed_data``；直接写入方的行不记委派链（``_propagate_content_writers``
    只给非直接写入方记），这一半写在裁决的 lane 文字里。
    """
    inventory = json.loads(_INVENTORY_PATH.read_text(encoding="utf-8"))
    row = next(e for e in inventory["entries"] if e["writer_id"] == _RESTORE_MANY)
    assert {"checklist_responses.remark", "checklist_responses.conclusion"} <= set(
        row["facts"]["sql_update_columns"]
    ), row["facts"]["sql_update_columns"]
    assert "checklist_responses" in row["content_stores_written"]
    assert row["adjudication"]["domain"] == "checklist_response_store"
    assert "write_cell_to_parsed_data" in row["adjudication"]["version_domain_note"]


def _variable_bound_writes(stores: dict[str, frozenset[str]]) -> dict[str, set[str]]:
    """独立现算：全仓 ``text(<名字>)`` 里，同函数内赋给该名字的 SQL 写了哪些内容列。

    不调用生成器的发现函数（否则判据和被测物同源）；只借用「内容存储 = 哪些表的哪些列」这一个定义。
    """
    import re

    found: dict[str, set[str]] = {}

    def columns(sql: str) -> set[str]:
        hit: set[str] = set()
        for table, cols in stores.items():
            for body in re.findall(rf"update\s+{table}\s+set\s+(.+?)(?:\s+where\b|$)", sql, re.I | re.S):
                hit |= {f"{table}.{c.lower()}" for c in re.findall(r"([a-z_][a-z0-9_]*)\s*=", body, re.I)
                        if c.lower() in cols}
            for body in re.findall(rf"insert\s+into\s+{table}\s*\(([^)]*)\)", sql, re.I | re.S):
                hit |= {f"{table}.{c.strip().lower()}" for c in re.split(r"[,\s]+", body)
                        if c.strip().lower() in cols}
        return hit

    for path in sorted(_APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        module = ".".join(path.relative_to(_BACKEND).with_suffix("").parts)
        stack: list[tuple[str, ast.AST]] = [("", tree)]
        while stack:
            prefix, parent = stack.pop()
            for child in ast.iter_child_nodes(parent):
                if isinstance(child, ast.ClassDef):
                    stack.append((f"{prefix}{child.name}.", child))
                    continue
                if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    stack.append((prefix, child))
                    continue
                qualname = f"{prefix}{child.name}"
                stack.append((f"{qualname}.", child))
                bound: dict[str, list[str]] = {}
                for node in ast.walk(child):
                    if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) \
                            and isinstance(node.value.value, str):
                        for target in node.targets:
                            if isinstance(target, ast.Name):
                                bound.setdefault(target.id, []).append(node.value.value)
                hit: set[str] = set()
                for node in ast.walk(child):
                    if isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", "")) == "text":
                        for argument in node.args:
                            if isinstance(argument, ast.Name):
                                for sql in bound.get(argument.id, []):
                                    hit |= columns(sql)
                if hit:
                    found[f"{module}::{qualname}"] = hit
    return found


def test_no_variable_bound_content_write_is_missing_from_the_inventory(generator: ModuleType) -> None:
    """全仓对账：任何经变量执行的内容写入，清册对应行的 sql_update_columns 都得含这些列。

    分母非空（restore_many 就是一例）⇒ 判据不会因扫描范围失效而恒绿。
    """
    found = _variable_bound_writes(generator._CONTENT_STORES)
    assert _RESTORE_MANY in found, sorted(found)
    rows = {
        e["writer_id"]: set(e["facts"]["sql_update_columns"])
        for e in json.loads(_INVENTORY_PATH.read_text(encoding="utf-8"))["entries"]
    }
    missing = {key: sorted(cols - rows.get(key, set())) for key, cols in found.items() if cols - rows.get(key, set())}
    assert missing == {}, f"清册漏掉了经变量执行的内容写入：{missing}"
