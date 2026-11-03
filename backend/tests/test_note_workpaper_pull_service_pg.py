"""真库：附注刷新从底稿取数（spec note-pull-header-formula-closure R2）。每个用例在最终回滚的事务里建数据。

判据：①推送对【测试】项目真实执行（试算表为空 ⇒ 不写、按原因回报，不抛）②已由底稿同步过的章节补
``_source=workpaper``、**不改同步时间**（没有同步就不算同步）③从未同步的章节原样不动 ④回传章节对应底稿 id。
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.models.report_models import ContentType, DisclosureNote
from app.services.note_workpaper_pull_service import pull_sections
from tests.procedure_delegation_visibility._factories import mk_project, mk_working_paper, mk_wp_index

IS_PG = settings.DATABASE_URL.startswith("postgresql")
pytestmark = [pytest.mark.pg_only, pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")]

YEAR = 2025


@pytest_asyncio.fixture
async def pg_session():
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    conn = await engine.connect()
    trans = await conn.begin()
    session = AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        await session.close()
        await trans.rollback()
        await conn.close()
        await engine.dispose()


async def _note(session, project_id, section: str, table_data: dict) -> DisclosureNote:
    note = DisclosureNote(project_id=project_id, year=YEAR, note_section=section, section_title=section,
                          content_type=ContentType.table, table_data=table_data)
    session.add(note)
    await session.flush()
    return note


async def test_pull_marks_only_synced_sections_and_reports_workpapers(pg_session):
    project = await mk_project(pg_session)
    project.template_type = "soe"
    project.audit_period_end = date(YEAR, 12, 31)
    index = await mk_wp_index(pg_session, project.id, wp_code="D2", audit_cycle="D")
    paper = await mk_working_paper(pg_session, project.id, index.id)
    synced = await _note(pg_session, project.id, "八、5", {"_last_sync_wp_id": str(paper.id),
                                                       "_last_sync_at": "2026-10-01T00:00:00+00:00",
                                                       "rows": []})
    never = await _note(pg_session, project.id, "八、1", {"rows": [], "_source": None})

    out = await pull_sections(pg_session, project.id, YEAR, sections=["八、5", "八、1"], user_id=None)

    await pg_session.refresh(synced)
    await pg_session.refresh(never)
    assert synced.table_data["_source"] == "workpaper"
    assert synced.table_data["_last_sync_at"] == "2026-10-01T00:00:00+00:00", "没有同步就不改同步时间"
    assert never.table_data == {"rows": [], "_source": None}, "从未同步的章节原样不动"
    assert (out["synced"], out["skipped_never_synced"]) == (1, 1)
    rows = {r["section"]: r for r in out["sections"]}
    assert rows["八、5"]["wp_ids"] == {"D2": str(paper.id)}
    assert rows["八、1"]["wp_codes"] == ["E1"] and rows["八、1"]["wp_ids"] == {}
    # 推送真实执行：空试算表不写任何附注格，且不因此报错
    assert out["push"]["wp_codes"] == ["D2", "E1"]
    assert out["push"]["error"] is None and out["push"]["written"] == 0
    still = (await pg_session.execute(sa.text("SELECT count(*) FROM disclosure_notes WHERE project_id = :p"),
                                      {"p": project.id})).scalar_one()
    assert still == 2, "推送不新建附注"


async def test_other_section_states_cover_notes_outside_the_refresh(pg_session):
    """全部刷新时其余章节的状态（R1.1）：与章节行同口径；排除的章节、软删的章节、别的年度不在内。"""
    from app.services.note_workpaper_pull_service import _other_section_states

    project = await mk_project(pg_session)
    await _note(pg_session, project.id, "八、5", {"rows": []})
    await _note(pg_session, project.id, "八、3", {"_last_sync_wp_id": "x", "rows": []})
    await _note(pg_session, project.id, "八、9", {"rows": [{"label": "甲", "values": [5.0, None],
                                                        "_cell_modes": {"0": "manual", "1": "manual"}}]})
    gone = await _note(pg_session, project.id, "八、7", {"rows": []})
    gone.is_deleted = True
    other_year = await _note(pg_session, project.id, "八、8", {"rows": []})
    other_year.year = YEAR - 1
    await pg_session.flush()

    states = await _other_section_states(pg_session, project.id, YEAR, {"八、5"})
    assert states == {
        "八、3": {"exists": True, "synced_before": True, "manual_values": 0},
        "八、9": {"exists": True, "synced_before": False, "manual_values": 1},
    }


async def test_pull_runs_note_formulas_on_refreshed_sections(pg_session):
    """推送后对刷新的章节执行附注公式（R3.4）：第 2 张表的合计 / 账面价值随明细更新，写进 ``_tables``。"""
    project = await mk_project(pg_session)
    project.template_type = "soe"
    project.audit_period_end = date(YEAR, 12, 31)
    aging = {"name": "（1）按账龄披露应收账款", "headers": ["账 龄", "期末数", "期初数"], "rows": [
        {"label": "1年以内", "values": [800.0, 600.0]}, {"label": "1至2年", "values": [200.0, 100.0]},
        {"label": "合 计", "values": [None, None], "is_total": True, "row_type": "total"}]}
    bad_debt = {"name": "（2）按坏账准备计提方法分类披露应收账款",
                "headers": ["类 别", "金额", "比例(%)", "金额", "预期信用损失率(%)", "账面价值"],
                "_column_groups": [{"group": "账面余额", "start": 1, "span": 2},
                                   {"group": "坏账准备", "start": 3, "span": 2}],
                "rows": [{"label": "按单项计提坏账准备", "values": [100.0, 10.0, 20.0, 20.0, None]},
                         {"label": "按组合计提坏账准备", "values": [900.0, 90.0, 45.0, 5.0, None]},
                         {"label": "合 计", "values": [None] * 5, "is_total": True, "row_type": "total"}]}
    note = await _note(pg_session, project.id, "八、5", {"headers": aging["headers"], "rows": aging["rows"],
                                                       "_tables": [aging, bad_debt]})

    out = await pull_sections(pg_session, project.id, YEAR, sections=["八、5"], user_id=None)

    await pg_session.refresh(note)
    t0, t1 = note.table_data["_tables"][0]["rows"], note.table_data["_tables"][1]["rows"]
    assert t0[2]["values"] == [1000.0, 700.0] and note.table_data["rows"][2]["values"] == [1000.0, 700.0]
    assert t1[2]["values"] == [1000.0, None, 65.0, None, 935.0]
    assert [r["values"][4] for r in t1[:2]] == [80.0, 855.0]
    assert out["formulas"]["updated"] == 2 + 3 + 2 and out["formulas"]["sections"] == ["八、5"]
    assert out["sections"][0]["formula_updated"] == 7 and out["formulas"]["errors"] == []


async def test_pull_reports_year_mismatch_instead_of_failing(pg_session):
    project = await mk_project(pg_session)
    project.template_type = "listed"
    project.audit_period_end = date(YEAR + 1, 12, 31)
    await pg_session.flush()
    out = await pull_sections(pg_session, project.id, YEAR, sections=["五、5"], user_id=uuid.uuid4())
    assert out["push"]["ran"] is False
    assert "审计年度" in (out["push"]["error"] or "")
