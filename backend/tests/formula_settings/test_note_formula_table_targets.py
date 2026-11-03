"""附注公式管理按表列出 / 改写预设（spec note-pull-header-formula-closure R3 任务 10~11）。SQLite 真 ORM。

判据：①多表章节第 2 张起的表也有预设，目标 ``t{n}:行:列``、带「表名 · 行名 · 列名」、按（表, 行, 列）数值排序
②列表回目标清单（弹窗选表 / 行 / 列）③原样保存不算适配；改写第 2 张表的预设 ⇒ 本项目适配 + 物化，执行器按它算。
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa

from app.models.report_models import DisclosureNote
from app.services.formula_settings import note_settings
from app.services.note_formula_generator import execute_note_formulas

from ._env import add_project, add_user, make_db

SECTION = "八、5"


def _row(label, values, **kw):
    return {"label": label, "values": values, **kw}


TABLES = [
    {"name": "（1）按账龄披露应收账款", "headers": ["账 龄", "期末数", "期初数"],
     "rows": [_row(f"第{i}段", [float(i), None]) for i in range(1, 11)]
             + [_row("合 计", [None, None], is_total=True, row_type="total")]},
    {"name": "（3）本期计提、收回或转回的坏账准备情况", "headers": ["类 别", "期初数", "本期计提", "期末数"],
     "rows": [_row("按单项计提", [1.0, 2.0, 3.0]), _row("按组合计提", [4.0, 5.0, 9.0]),
              _row("合 计", [None, None, None], is_total=True, row_type="total")]},
]


async def _add_note(db, pid) -> uuid.UUID:
    note_id = uuid.uuid4()
    db.add(DisclosureNote(id=note_id, project_id=pid, year=2025, note_section=SECTION, section_title="应收账款",
                          table_data={"headers": TABLES[0]["headers"], "rows": TABLES[0]["rows"], "_tables": TABLES}))
    await db.flush()
    return note_id


async def test_listing_has_every_table_with_readable_targets():
    async with make_db([DisclosureNote]) as factory, factory() as db:
        pid = await add_project(db, "甲")
        await _add_note(db, pid)
        listing = await note_settings.list_section(db, pid, 2025, SECTION)

        targets = [r["target"] for r in listing["formulas"]]
        assert targets == ["10:0", "10:1", "t1:2:0", "t1:2:1", "t1:2:2"], "预设按结构生成（期初列现在没数也有公式）"
        assert listing["formulas"][2]["target_label"] == "（3）本期计提、收回或转回的坏账准备情况 · 合 计 · 期初数"
        assert all(r["layer"] == "preset" for r in listing["formulas"])
        assert [t["name"] for t in listing["targets"]] == [TABLES[0]["name"], TABLES[1]["name"]]
        assert listing["targets"][1]["columns"] == ["期初数", "本期计提", "期末数"]


def test_targets_sort_numerically_by_table_row_col():
    from app.services.note_formula_service import target_sort_key

    recs = [{"target": t} for t in ("t1:0:0", "10:0", "R1", "2:0", "2:1")]
    assert [r["target"] for r in sorted(recs, key=target_sort_key)] == ["2:0", "2:1", "10:0", "t1:0:0", "R1"]


async def test_editing_a_second_table_preset_becomes_project_adaptation():
    async with make_db([DisclosureNote]) as factory, factory() as db:
        user = await add_user(db, "u")
        pid = await add_project(db, "甲")
        note_id = await _add_note(db, pid)
        listing = await note_settings.list_section(db, pid, 2025, SECTION)

        unchanged = await note_settings.save_section(db, pid, 2025, SECTION, listing["formulas"],
                                                     loaded=listing["loaded"], user_id=user.id)
        assert unchanged["events"] == [], "与预设相同：不算适配"

        edited = [dict(r, formula="cell(0,0) + cell(1,0) + 100") if r["target"] == "t1:2:0" else r
                  for r in listing["formulas"]]
        saved = await note_settings.save_section(db, pid, 2025, SECTION, edited, loaded=listing["loaded"],
                                                 user_id=user.id)
        row = next(r for r in saved["formulas"] if r["target"] == "t1:2:0")
        assert row["layer"] == "project" and row["formula"].endswith("+ 100")

        await execute_note_formulas(db, pid, 2025, SECTION)
        td = (await db.execute(sa.select(DisclosureNote.table_data).where(DisclosureNote.id == note_id)
                               .execution_options(populate_existing=True))).scalar_one()
        assert td["_tables"][1]["rows"][2]["values"] == [105.0, 7.0, 12.0], "改写的公式执行；其余列按预设合计"
        assert td["_tables"][0]["rows"][10]["values"][0] == 55.0
