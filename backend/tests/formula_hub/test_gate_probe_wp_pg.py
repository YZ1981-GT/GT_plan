"""一致性门禁取数探测 ``_probe_wp`` 的五种状态（真 PG，回滚事务）。

原实现在「底稿 parsed_data 为空」分支导入不存在的 ``ChecklistResponse`` ORM（该表只有裸 SQL 访问），并用 wp_index 的 id
去比 ``checklist_responses.wp_id``（外键指向 ``working_paper.id``）⇒ 一走到该分支就 ImportError，即便修好导入也永远数到 0。
lazy import 守卫在阶段 B 回归里抓出（spec formula-hub-integrity-closure 需求 16.2，ADR-FHIC-14 第 2 点）。
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text

from app.services.consistency_gate._helpers import _probe_wp
from tests.formula_hub.gate_fixtures import seed_test_project

pytestmark = pytest.mark.pg_only


async def _wp(db, pid, code: str, *, parsed: str | None, deleted: bool = False):
    idx, wp = uuid4(), uuid4()
    await db.execute(text("INSERT INTO wp_index (id, project_id, wp_code, wp_name) VALUES (:i, :p, :c, :c)"),
                     {"i": idx, "p": pid, "c": code})
    await db.execute(text(
        "INSERT INTO working_paper (id, project_id, wp_index_id, file_path, source_type, parsed_data, is_deleted) "
        "VALUES (:w, :p, :i, :f, 'template', CAST(:d AS jsonb), :del)"),
        {"w": wp, "p": pid, "i": idx, "f": f"fh/{code}.xlsx", "d": parsed, "del": deleted})
    return wp


@pytest.mark.asyncio
async def test_probe_wp_states(pg_tx):
    db = pg_tx
    pid, _year = await seed_test_project(db, name="【测试】FH-probe-wp")
    await _wp(db, pid, "FHP1", parsed='{"a": 1}')
    await _wp(db, pid, "FHP2", parsed=None)
    form_wp = await _wp(db, pid, "FHP3", parsed=None)
    await db.execute(text("INSERT INTO checklist_responses (id, project_id, wp_id, item_id) VALUES (:id, :p, :w, 'x')"),
                     {"id": uuid4(), "p": pid, "w": form_wp})
    await _wp(db, pid, "FHP4", parsed='{"a": 1}', deleted=True)
    await db.flush()

    states = {code: (await _probe_wp(db, pid, code)).state for code in ("FHP1", "FHP2", "FHP3", "FHP4", "FHP9")}
    assert states == {"FHP1": "present", "FHP2": "empty", "FHP3": "empty_form", "FHP4": "trimmed", "FHP9": "absent"}
