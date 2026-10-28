# -*- coding: utf-8 -*-
"""存量程序表字段覆盖位置修复工具（spec audit-year-calendar-fallback-ratchet 任务 0.5）。

缺陷：执行人改的状态 / 执行说明按今年（2026）写、scope 用表名（「审计程序A7」），读取方按项目审计年度与表码读
⇒ 刷新后看不到。工具把这些行挪到读取方的位置；目标位置已有值（含两行错位到同一目标）一律不动、单列冲突。
真实 PostgreSQL 回滚事务（唯一约束 project_id + year + scope + item_key + field 只有真库测得到）；只处理本测试建的项目。
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.models.base import ProjectStatus
from app.models.core import Project
from app.models.workpaper_field_override_models import WorkpaperFieldOverride as O
from scripts.fix import fix_program_override_placement as fix

pytestmark = [pytest.mark.asyncio,
              pytest.mark.skipif(not settings.DATABASE_URL.startswith("postgresql"), reason="need PostgreSQL")]


@pytest_asyncio.fixture
async def world():
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    conn = await engine.connect()
    trans = await conn.begin()
    db = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        def _project(name, year):
            return Project(name=f"【测试】覆盖位置修复{name}", client_name="【测试】覆盖位置修复", status=ProjectStatus.execution,
                           template_type="soe", report_scope="standalone", audit_year=year, scenario="normal")
        p, no_year, other = _project("_2025", 2025), _project("_无年度", None), _project("_其他", 2025)
        db.add_all([p, no_year, other])
        await db.flush()
        rows = {
            "a7": O(project_id=p.id, year=2026, scope="procedure_table:审计程序A7", item_key="3",
                    field="execution_summary", value="补充说明"),
            "k1a": O(project_id=p.id, year=2026, scope="procedure_table:K1A", item_key="1", field="status",
                     value="completed"),
            "a1_old": O(project_id=p.id, year=2026, scope="procedure_table:A1", item_key="5",
                        field="execution_summary", value="旧"),
            "a1_new": O(project_id=p.id, year=2025, scope="procedure_table:A1", item_key="5",
                        field="execution_summary", value="新"),
            # 两行错位到同一目标（2025, A8）：按定序第一行占位，第二行算冲突
            "a8_scope": O(project_id=p.id, year=2026, scope="procedure_table:A8", item_key="2",
                          field="execution_summary", value="甲"),
            "a8_both": O(project_id=p.id, year=2026, scope="procedure_table:审计程序A8", item_key="2",
                         field="execution_summary", value="乙"),
            "ok": O(project_id=p.id, year=2025, scope="procedure_table:H1A", item_key="2", field="status",
                    value="in_progress"),
            "not_program": O(project_id=p.id, year=2026, scope="review:A23", item_key="1", field="status", value="x"),
            "no_year": O(project_id=no_year.id, year=2026, scope="procedure_table:审计程序A7", item_key="1",
                         field="status", value="completed"),
            "other": O(project_id=other.id, year=2026, scope="procedure_table:审计程序A7", item_key="1",
                       field="status", value="completed"),
        }
        db.add_all(rows.values())
        await db.flush()
        yield {"db": db, "rows": rows, "pids": [str(p.id), str(no_year.id)]}
    finally:
        await db.close()
        await trans.rollback()
        await conn.close()
        await engine.dispose()


async def _places(db, rows) -> dict[str, tuple[int, str]]:
    found = {rid: (year, scope) for rid, year, scope in (await db.execute(
        sa.select(O.id, O.year, O.scope).where(O.id.in_([r.id for r in rows.values()]))
    )).all()}
    return {name: found[r.id] for name, r in rows.items()}


_EXPECTED_MOVES = {"a7": (2025, "procedure_table:A7"), "k1a": (2025, "procedure_table:K1A"),
                   "a8_scope": (2025, "procedure_table:A8"), "no_year": (2026, "procedure_table:A7")}


async def test_dry_run_reports_without_writing(world):
    db, rows = world["db"], world["rows"]
    before = await _places(db, rows)
    report = await fix.fix_placement(db, apply=False, project_ids=world["pids"])
    ids = {str(r.id): name for name, r in rows.items()}
    assert {ids[e["id"]] for e in report["skipped"]} == set(_EXPECTED_MOVES)
    assert {ids[e["id"]] for e in report["conflicts"]} == {"a1_old", "a8_both"}, "目标已有值 / 两行同一目标都算冲突"
    assert report["moved"] == [] and await _places(db, rows) == before


async def test_apply_moves_to_reader_place_and_leaves_conflicts(world):
    db, rows = world["db"], world["rows"]
    before = await _places(db, rows)
    dry = await fix.fix_placement(db, apply=False, project_ids=world["pids"])
    report = await fix.fix_placement(db, apply=True, project_ids=world["pids"])
    after = await _places(db, rows)

    assert {e["id"] for e in report["moved"]} == {e["id"] for e in dry["skipped"]}, "预演与执行的结论须一致"
    for name, place in after.items():
        assert place == _EXPECTED_MOVES.get(name, before[name]), name
    # 留痕：平台操作日志 logs，列出每行的来去
    detail = (await db.execute(sa.text(
        "SELECT new_value FROM logs WHERE action_type = 'fix_program_override_placement' "
        "AND new_value::text LIKE :rid ORDER BY created_at DESC LIMIT 1"
    ), {"rid": f"%{rows['a7'].id}%"})).scalar_one()
    assert detail["moved_count"] == 4 and detail["conflict_count"] == 2
    assert {e["id"] for e in detail["entries"]} == {str(rows[n].id) for n in _EXPECTED_MOVES}
