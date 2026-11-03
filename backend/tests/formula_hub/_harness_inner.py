"""``test_pg_harness.py`` 以子进程按 node id 运行的内层用例。

文件名不以 ``test_`` 开头：常规收集（``pytest tests/formula_hub``）不会选中；命令行显式给出路径时 pytest 照常收集。
外层经环境变量传参：``FH_HARNESS_MARKER`` = 本次写入的【测试】项目名；``FH_HARNESS_OUT`` = 观测结果 JSON 的路径。
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from app.models.core import Project
from app.models.formula_setting_models import FormulaSyncItem
from tests.formula_hub._pg_harness import TEST_PROJECT_PREFIX, make_engine

pytestmark = pytest.mark.pg_only


def _write_out(payload: dict) -> None:
    Path(os.environ["FH_HARNESS_OUT"]).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


async def _count_on_other_connection(sql: str, **params) -> int:
    """另开引擎与连接读（READ COMMITTED：只看得到已提交的行）。"""
    engine = make_engine()
    try:
        async with engine.connect() as conn:
            return (await conn.execute(text(sql), params)).scalar_one()
    finally:
        await engine.dispose()


async def test_inner_pg_tx_write(pg_tx):
    name = os.environ["FH_HARNESS_MARKER"]
    pg_tx.add(Project(name=name, client_name=f"{TEST_PROJECT_PREFIX}公式中枢测试基座"))
    await pg_tx.commit()  # create_savepoint：只释放保存点，外层事务仍未提交
    sql = "SELECT count(*) FROM projects WHERE name = :name"
    in_tx = (await pg_tx.execute(text(sql), {"name": name})).scalar_one()
    elsewhere = await _count_on_other_connection(sql, name=name)
    _write_out({"in_tx": in_tx, "other_connection_during_tx": elsewhere})
    assert (in_tx, elsewhere) == (1, 0)


async def test_inner_committed_project(committed_project):
    handle = committed_project
    item = FormulaSyncItem(
        project_id=handle.project_id, domain="report", slot_key=f"fh_harness:{uuid.uuid4().hex[:8]}",
        reason="deferred",
    )
    await handle.add(item)
    visible = {
        "projects": await _count_on_other_connection(
            "SELECT count(*) FROM projects WHERE id = :pid", pid=handle.project_id),
        "formula_sync_item": await _count_on_other_connection(
            "SELECT count(*) FROM formula_sync_item WHERE id = :iid", iid=item.id),
    }
    _write_out({
        "project_id": str(handle.project_id), "project_name": handle.name, "sync_item_id": str(item.id),
        "tracked_tables": [table for table, _ in handle.tracked], "visible_from_other_connection": visible,
    })
    assert visible == {"projects": 1, "formula_sync_item": 1}


async def test_inner_committed_guard(committed_project):
    """守卫生效时夹具在建项目之前就失败，本函数体不会执行。"""
    _write_out({"reached_body": True})
