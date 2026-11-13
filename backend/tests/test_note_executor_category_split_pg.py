# -*- coding: utf-8 -*-
"""S2 check-contract-and-note-executor 任务 2 的真 PG 验收（ADR-CCN-02）。

在真实 PostgreSQL 上验证 ``execute_note_formulas`` 的类别分流：

- 手工格（有值、无单元格模式、值与上次写入值 ``last_value`` 不同）执行后值不变；
- ``logic_check`` 公式只产出 ``checks``，目标格不回写；
- ``auto_calc`` 公式回写正确的合计值；
- 返回体含 ``checks``。

数据：回滚事务内新建一个【测试】项目与一个附注章节（``disclosure_notes``）。不复用共享库里已有的【测试】附注，
因为要的是确定的手工格 / 校对格取值；事务不提交，夹具收尾回滚，并在回滚后用新连接核对项目没有残留。
"""
from __future__ import annotations

import copy
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.models.base import ProjectStatus
from app.models.core import Project
from app.models.report_models import DisclosureNote
from app.services.note_formula_generator import execute_note_formulas

_YEAR = 2025
_SECTION = "五、1"

pytestmark = [
    pytest.mark.pg_only,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not str(settings.DATABASE_URL).startswith("postgres"),
        reason="DATABASE_URL 不是 PostgreSQL，无法做真库回滚验收（需 DATABASE_URL 指向 PostgreSQL）",
    ),
]


def _table() -> dict:
    """存储形状与生产一致：``_tables[0]`` 为表，顶层 ``rows`` 为第一张表的镜像。

    行布局（两列：列 0 金额、列 1 校对列）：
    - 行 0 / 1：子项，有数值；
    - 行 2 ``合计``：列 0 为 auto_calc 目标（空，应被回写为子项之和 300）；列 1 为 logic_check 目标（手填 999，
      子项之和为 30，应只产出未通过的校对结果、不回写）；
    - 行 3 ``手工值``：列 0 为手工格（有值 999、无模式、上次写入值 100 与之不同，应保持 999）。
    """
    rows = [
        {"label": "子项甲", "values": [100.0, 10.0]},
        {"label": "子项乙", "values": [200.0, 20.0]},
        {"label": "合计", "values": [None, 999.0]},
        {"label": "手工值", "values": [999.0, None]},
    ]
    return {"headers": ["项目", "金额", "校对"], "rows": rows}


def _table_data() -> dict:
    table = _table()
    return {
        "_tables": [table],
        "rows": copy.deepcopy(table["rows"]),
        "headers": list(table["headers"]),
        "_formulas": {
            "2:0": {"type": "vertical_sum", "expression": "SUM(0:1, 0)", "category": "auto_calc"},
            "2:1": {"type": "vertical_sum", "expression": "SUM(0:1, 1)", "category": "logic_check",
                    "description": "合计勾稽"},
            "3:0": {"type": "vertical_sum", "expression": "SUM(0:1, 0)", "category": "auto_calc",
                    "last_value": 100.0},
        },
    }


@pytest_asyncio.fixture
async def world():
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    try:
        conn = await engine.connect()
    except OSError as exc:
        await engine.dispose()
        pytest.skip(f"PostgreSQL 不可达，本用例未运行：{type(exc).__name__}: {exc}")
    marker = f"【测试】附注执行器分流{uuid.uuid4().hex[:8]}"
    trans = await conn.begin()
    db = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        project = Project(
            name=marker, client_name=marker, status=ProjectStatus.execution,
            template_type="soe", report_scope="standalone", audit_year=_YEAR, scenario="normal",
        )
        db.add(project)
        await db.flush()
        note = DisclosureNote(
            project_id=project.id, year=_YEAR, note_section=_SECTION,
            section_title="【测试】附注执行器分流", table_data=_table_data(),
        )
        db.add(note)
        await db.flush()
        yield {"db": db, "note_id": note.id, "project_id": project.id}
    finally:
        await db.close()
        await trans.rollback()
        await conn.close()
    # 回滚后用新连接核对：【测试】项目不应残留在共享库（写入只在回滚事务内）
    async with engine.connect() as probe:
        leaked = await probe.scalar(
            sa.text("SELECT count(*) FROM projects WHERE name = :name"), {"name": marker},
        )
    await engine.dispose()
    assert leaked == 0, f"回滚后仍能查到【测试】项目 {marker!r}，写入泄漏到了事务外"


@pytest.mark.asyncio
async def test_category_split_on_real_pg_manual_cell_kept_and_check_not_written(world):
    db = world["db"]
    note_id = world["note_id"]
    project_id = world["project_id"]

    result = await execute_note_formulas(db, project_id, _YEAR, _SECTION)
    await db.flush()

    # 从数据库读回（事务内已落库的值），而不是读 ORM 对象的内存状态
    stored = (await db.execute(sa.select(DisclosureNote.table_data).where(DisclosureNote.id == note_id))).scalar_one()
    rows = stored["_tables"][0]["rows"]

    # auto_calc：空目标回写为子项之和，量化到分
    assert rows[2]["values"][0] == 300.0
    # 手工格：有值、无模式、与上次写入值不同 ⇒ 保持 999
    assert rows[3]["values"][0] == 999.0
    # logic_check：目标格不回写，手填值保持 999
    assert rows[2]["values"][1] == 999.0
    # 顶层镜像随第一张表同步
    assert stored["rows"][2]["values"][0] == 300.0

    assert result["updated"] == 1
    statuses = {item["cell"]: item["status"] for item in result["results"]}
    assert statuses["2:0"] == "ok"
    assert statuses["3:0"] == "skipped_manual"
    assert statuses["2:1"] == "skipped"

    # 结果含 checks：logic_check 产出一条未通过的校对结果，左右两侧为子项之和与手填值
    assert "checks" in result
    checks = {item["rule_id"]: item for item in result["checks"]}
    assert set(checks) == {"2:1"}
    check = checks["2:1"]
    assert check["status"] == "failed"
    assert check["label"] == "未通过"
    assert check["severity"] == "warning"
    assert check["left"] == 30.0
    assert check["right"] == 999.0
    assert check["diff"] == 969.0
