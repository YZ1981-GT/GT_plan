"""应用范围放开到底稿域（spec formula-management-repair-closure R4）。

「应用到指定项目」：有这张底稿的目标写成本项目适配；没有这张底稿的目标，底稿写入方无处可写（会静默跳过），
所以必须列进 ``skipped``（带项目名与原因），不算「已应用」、不发联动事件。作用范围过滤（合并附注对单体项目）的原因按域生成。
SQLite 真 ORM，真实存储落库再读回。
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa

from app.models.consol_push_models import ConsolNoteFormula
from app.models.workpaper_models import WorkingPaper, WpFormula, WpIndex, WpSourceType
from app.services.formula_settings import apply_ops
from app.services.formula_settings.engine import Decisions

from ._env import add_project, make_db

EXTRA = [WpIndex, WorkingPaper, WpFormula, ConsolNoteFormula]
SHEET, CELL = "审定表D2-1", "E8"
SLOT = f"D2|{SHEET}|{CELL}"
MINE = "TB('1122','期末余额')-TB('1231','期末余额')"


async def _add_wp(db, project_id, code: str = "D2") -> uuid.UUID:
    idx = WpIndex(id=uuid.uuid4(), project_id=project_id, wp_code=code, wp_name=code)
    db.add(idx)
    await db.flush()
    wp = WorkingPaper(id=uuid.uuid4(), project_id=project_id, wp_index_id=idx.id, file_path=f"/tmp/{code}.xlsx",
                      source_type=WpSourceType.template)
    db.add(wp)
    await db.flush()
    return wp.id


async def _rows(db, project_id) -> list[WpFormula]:
    return list((await db.execute(sa.select(WpFormula).where(WpFormula.project_id == project_id))).scalars().all())


async def _world(db):
    src, with_wp, without_wp = [await add_project(db, n) for n in ("甲", "乙", "丙")]
    src_wp = await _add_wp(db, src)
    await _add_wp(db, with_wp)
    await _add_wp(db, without_wp, "E1")  # 有别的底稿，没有 D2
    db.add(WpFormula(id=uuid.uuid4(), project_id=src, wp_id=src_wp, sheet_name=SHEET, target_cell=CELL,
                     expression=MINE, formula_type="auto_calc", formula_source="custom", definition_version=1))
    await db.commit()
    return src, with_wp, without_wp


async def test_preview_lists_targets_without_the_workpaper_as_skipped():
    async with make_db(EXTRA) as factory, factory() as db:
        src, with_wp, without_wp = await _world(db)
        preview = await apply_ops.apply_preview(db, domain="wp", project_id=src, slot_keys=[SLOT],
                                                target_ids=[with_wp, without_wp])
    assert {i["project_id"] for i in preview["items"]} == {str(with_wp)}
    assert preview["skipped"] == [{"project_id": str(without_wp), "project_name": "丙", "slot_key": SLOT,
                                   "reason": "该项目没有底稿 D2，无处写入（建这张底稿时按全局 / 系统预设预填）"}]


async def test_apply_writes_only_where_the_workpaper_exists_and_reports_the_rest():
    async with make_db(EXTRA) as factory, factory() as db:
        src, with_wp, without_wp = await _world(db)
        out = await apply_ops.apply_to_projects(db, domain="wp", project_id=src, slot_keys=[SLOT],
                                                target_ids=[with_wp, without_wp], decisions=Decisions(), user_id=None)
        await db.commit()
        written = await _rows(db, with_wp)
        assert [(r.sheet_name, r.target_cell, r.expression) for r in written] == [(SHEET, CELL, MINE)]
        assert await _rows(db, without_wp) == []
    assert out["summary"]["target_count"] == 1, "没有这张底稿的项目不算已应用"
    assert [e["project_id"] for e in out["events"]] == [str(with_wp)], "跳过的项目不发联动事件"
    assert [s["project_id"] for s in out["skipped"]] == [str(without_wp)]


async def test_scope_filtered_reason_is_generated_per_domain():
    assert apply_ops._not_applicable_reason("consol_note") == "该项目不是合并项目，不适用合并附注公式"
    assert apply_ops._not_applicable_reason("wp").startswith("该项目不适用")
