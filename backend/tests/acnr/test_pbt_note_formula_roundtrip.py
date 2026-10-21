# Feature: acnr-consumer-wiring, Property 20: Formula Dialog Edit Persistence Round-Trip
"""Property + unit tests for NoteFormulaService (P10 / Task 20.3)，按公式全局设置后的契约重写。

**Property 20: Formula Dialog Edit Persistence Round-Trip**

*For any* 一组附注公式编辑经 ``NoteFormulaService.save_many`` 保存后，用 ``list_by_section``
重新载入同一章节 SHALL 返回同一组公式（不丢、不被静默重生成）。

契约变化（spec formula-global-settings-sync，R6 / R10）：保存不再整体覆盖 ``_user_formulas``，
而是按载入时的版本令牌（``list_with_versions`` 的 ``loaded``）求差量写本项目适配
（``formula_setting``），再把有效集合物化进 ``_user_formulas``；载入 = 本项目适配 > 全局 >
该表模板公式。原来基于假会话（``_FakeDB`` 只回同一个对象）的测试测不到这条链，改用 SQLite 真 ORM。

**Validates: Requirements 15.1, 15.2, 15.4**
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa
from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.report_models import DisclosureNote
from app.services.note_formula_service import NoteFormulaService, _USER_FORMULAS_KEY, _VALID_CATEGORIES
from tests.formula_settings._env import add_project, make_db

SECTION = "五、3"
EXTRA = [DisclosureNote]
REQUIRED_KEYS = {"target", "formula", "description", "category", "source", "type", "layer"}


def _run(coro):
    return asyncio.run(coro)


async def _add_note(db, project_id, table_data: dict | None) -> uuid.UUID:
    note = DisclosureNote(id=uuid.uuid4(), project_id=project_id, year=2025, note_section=SECTION,
                          section_title="应收账款", table_data=table_data, is_deleted=False)
    db.add(note)
    await db.flush()
    return note.id


async def _note(db, note_id) -> DisclosureNote:
    return (await db.execute(sa.select(DisclosureNote).where(DisclosureNote.id == note_id)
                             .execution_options(populate_existing=True))).scalar_one()


async def _save(svc, db, pid, records):
    """按弹窗的真实调用方式：先载入拿版本令牌，再带令牌保存。"""
    loaded = (await svc.list_with_versions(db, pid, 2025, SECTION))["loaded"]
    return await svc.save_many(db, pid, 2025, SECTION, records, loaded=loaded)


def _core(rows):
    return [(r["target"], r["formula"], r["category"]) for r in rows]


# 无空白安全字符集（strip 后仍非空）
_SAFE = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-'(),.:期末余额审定合计"
_CATEGORY_ST = st.one_of(st.sampled_from(_VALID_CATEGORIES), st.sampled_from(["", "bogus", "logic", None]))


@st.composite
def _formula_record(draw) -> dict:
    return {
        "target": "R" + draw(st.text(alphabet=_SAFE, min_size=1, max_size=8)),  # 目标格必填（公式位身份）
        "formula": draw(st.text(alphabet=_SAFE, min_size=1, max_size=24)),
        "description": draw(st.text(alphabet=_SAFE, min_size=0, max_size=20)),
        "category": draw(_CATEGORY_ST),
        "source": draw(st.text(alphabet=_SAFE, min_size=0, max_size=10)),
        "_editing": draw(st.booleans()),  # 前端本地态，必须被剔除
    }


_RECORDS = st.lists(_formula_record(), min_size=1, max_size=8, unique_by=lambda r: r["target"])


class TestProperty20RoundTrip:
    @given(records=_RECORDS)
    @settings(max_examples=5, deadline=None)
    def test_save_reload_is_identity(self, records):
        async def body():
            async with make_db(EXTRA) as factory, factory() as db:
                pid = await add_project(db, "往返")
                nid = await _add_note(db, pid, {"_formulas": {"0:1": {"expression": "SUM(x)"}}})
                svc = NoteFormulaService()
                saved = await _save(svc, db, pid, records)
                reloaded = await svc.list_by_section(db, pid, 2025, SECTION)
                assert reloaded == saved
                mine = [r for r in reloaded if r["layer"] == "project"]
                assert {r["target"] for r in mine} == {r["target"] for r in records}, "保存的每条都在、没被模板预览顶掉"
                assert [r["target"] for r in (await _note(db, nid)).table_data[_USER_FORMULAS_KEY]] == \
                    sorted(r["target"] for r in mine), "有效集合物化进 _user_formulas（执行器读这里）"
        _run(body())

    @given(records=_RECORDS)
    @settings(max_examples=5, deadline=None)
    def test_reload_normalized_shape_stable(self, records):
        async def body():
            async with make_db(EXTRA) as factory, factory() as db:
                pid = await add_project(db, "形状")
                await _add_note(db, pid, {})
                svc = NoteFormulaService()
                saved = await _save(svc, db, pid, records)
                reloaded = await svc.list_by_section(db, pid, 2025, SECTION)
                assert reloaded == saved
                for rec in reloaded:
                    assert REQUIRED_KEYS <= set(rec)
                    assert "_editing" not in rec
                    assert rec["category"] in _VALID_CATEGORIES
                    assert rec["formula"].strip()
        _run(body())

    @given(records=_RECORDS)
    @settings(max_examples=5, deadline=None)
    def test_idempotent_double_save(self, records):
        async def body():
            async with make_db(EXTRA) as factory, factory() as db:
                pid = await add_project(db, "幂等")
                await _add_note(db, pid, {})
                svc = NoteFormulaService()
                first = await _save(svc, db, pid, records)
                second = await _save(svc, db, pid, first)
                reloaded = await svc.list_by_section(db, pid, 2025, SECTION)
                assert _core(first) == _core(second) == _core(reloaded)
        _run(body())


class TestListBySection:
    def test_project_adaptation_takes_priority_over_template_preview(self):
        async def body():
            async with make_db(EXTRA) as factory, factory() as db:
                pid = await add_project(db, "优先")
                await _add_note(db, pid, {"_formulas": {"0:1": {"expression": "SUM(preview)"}}})
                svc = NoteFormulaService()
                await _save(svc, db, pid, [{"target": "0:1", "formula": "TB('1122','审定数')"}])
                out = await svc.list_by_section(db, pid, 2025, SECTION)
                assert [(r["target"], r["formula"], r["layer"]) for r in out] == [
                    ("0:1", "TB('1122','审定数')", "project")]
        _run(body())

    def test_falls_back_to_formulas_preview_when_no_user_set(self):
        async def body():
            async with make_db(EXTRA) as factory, factory() as db:
                pid = await add_project(db, "预览")
                await _add_note(db, pid, {"_formulas": {"2:3": {"expression": "SUM(A1:A2)", "description": "小计",
                                                                "category": "auto_calc"}}})
                out = await NoteFormulaService().list_by_section(db, pid, 2025, SECTION)
                assert [(r["target"], r["formula"], r["layer"]) for r in out] == [("2:3", "SUM(A1:A2)", "preset")]
        _run(body())

    def test_empty_when_note_missing(self):
        async def body():
            async with make_db(EXTRA) as factory, factory() as db:
                pid = await add_project(db, "无附注")
                assert await NoteFormulaService().list_by_section(db, pid, 2025, SECTION) == []
        _run(body())

    def test_empty_when_no_table_data(self):
        async def body():
            async with make_db(EXTRA) as factory, factory() as db:
                pid = await add_project(db, "无表")
                await _add_note(db, pid, None)
                assert await NoteFormulaService().list_by_section(db, pid, 2025, SECTION) == []
        _run(body())


class TestSaveMany:
    def test_edit_persists_across_reopen(self):
        async def body():
            async with make_db(EXTRA) as factory:
                async with factory() as db:
                    pid = await add_project(db, "重开")
                    await _add_note(db, pid, {})
                    saved = await _save(NoteFormulaService(), db, pid, [
                        {"target": "R1", "formula": "TB('1122','审定数')", "description": "应收合计",
                         "category": "auto_calc", "source": "TB"},
                        {"target": "R2", "formula": "NOTE('五、3','合计','期末')", "category": "logic_check"},
                    ])
                    await db.commit()
                async with factory() as db2:  # 模拟关闭再打开：新会话、新 service
                    reopened = await NoteFormulaService().list_by_section(db2, pid, 2025, SECTION)
                assert reopened == saved
                assert _core(reopened) == [("R1", "TB('1122','审定数')", "auto_calc"),
                                           ("R2", "NOTE('五、3','合计','期末')", "logic_check")]
        _run(body())

    def test_empty_rows_filtered(self):
        async def body():
            async with make_db(EXTRA) as factory, factory() as db:
                pid = await add_project(db, "空行")
                await _add_note(db, pid, {})
                out = await _save(NoteFormulaService(), db, pid, [
                    {"target": "R1", "formula": "TB('1001','期末余额')"},
                    {"target": "R2", "formula": "   "},
                    {"target": "", "formula": "TB('1002','期末余额')"},
                ])
                assert [r["target"] for r in out] == ["R1"]
        _run(body())

    def test_local_editing_field_stripped(self):
        async def body():
            async with make_db(EXTRA) as factory, factory() as db:
                pid = await add_project(db, "本地态")
                nid = await _add_note(db, pid, {})
                await _save(NoteFormulaService(), db, pid, [
                    {"target": "R1", "formula": "TB('1001','期末余额')", "_editing": True, "_dirty": 1}])
                stored = (await _note(db, nid)).table_data[_USER_FORMULAS_KEY]
                assert all(not k.startswith("_") for rec in stored for k in rec)
        _run(body())

    def test_invalid_category_normalized(self):
        async def body():
            async with make_db(EXTRA) as factory, factory() as db:
                pid = await add_project(db, "类别")
                await _add_note(db, pid, {})
                out = await _save(NoteFormulaService(), db, pid, [
                    {"target": "R1", "formula": "TB('1001','期末余额')", "category": "bogus"}])
                assert out[0]["category"] == "auto_calc"
        _run(body())

    def test_flush_called_not_commit(self):
        async def body():
            async with make_db(EXTRA) as factory, factory() as db:
                pid = await add_project(db, "只 flush")
                await _add_note(db, pid, {})
                db.commit = AsyncMock(side_effect=AssertionError("service 不得 commit"))
                await _save(NoteFormulaService(), db, pid, [{"target": "R1", "formula": "TB('1001','期末余额')"}])
                db.commit.assert_not_called()
        _run(body())

    def test_missing_note_raises_value_error(self):
        async def body():
            async with make_db(EXTRA) as factory, factory() as db:
                pid = await add_project(db, "缺附注")
                with pytest.raises(ValueError):
                    await NoteFormulaService().save_many(db, pid, 2025, SECTION, [
                        {"target": "R1", "formula": "TB('1001','期末余额')"}], loaded={})
        _run(body())
