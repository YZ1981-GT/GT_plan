"""国企 ↔ 上市转换只改系统标题：人工改过的章节标题 / 科目名保留并上报；快照与回滚覆盖这两列。

spec 49 Phase 8 加固（语义审查 #8）：原实现无条件 ``note.section_title = target_title``，审计师改过的标题
一转换就被模板值覆盖。判据：已知系统标题 = 源节与目标节的 ``known_titles``（现名、口径名、``legacy_titles``）。
"""
from __future__ import annotations

import pytest

from app.services.note_conversion_service import (
    NoteConversionService,
    plan_title_fields,
    revert_title_fields,
)
from tests.services.test_note_conversion_section_mapping_production import PROJECT, YEAR, make_note
from tests.test_note_conversion_preview_rollback import ConversionSession, _forward, _rollback
from tests.test_note_conversion_section_mapping import _Fx

SRC = {"section_id": "s", "section_title": "营业收入与营业成本", "legacy_titles": ["营业收入及营业成本"],
       "account_name": "营业收入与营业成本"}
TGT = {"section_id": "t", "section_title": "营业收入和营业成本", "account_name": "营业收入和营业成本"}


def _plan(title, account=None, *, target=TGT, target_title="营业收入和营业成本"):
    return plan_title_fields(title, account, source=SRC, target=target, source_title=SRC["section_title"],
                             target_title=target_title)


@pytest.mark.parametrize("title", ["营业收入与营业成本", "营业收入及营业成本", "营业收入和营业成本"])
def test_system_titles_move_to_target_title(title):
    out = _plan(title)
    assert out["section_title"] == "营业收入和营业成本" and out["title_kept"] is None


def test_manual_title_is_kept_and_reported():
    out = _plan("主营业务收支（审计师改）")
    assert out["section_title"] == "主营业务收支（审计师改）"
    assert out["title_kept"] == {"title": "主营业务收支（审计师改）", "template_title": "营业收入和营业成本"}


def test_account_name_follows_only_system_values():
    assert _plan("营业收入与营业成本", "营业收入与营业成本")["account_name"] == "营业收入和营业成本"
    manual = _plan("营业收入与营业成本", "自定义科目")
    assert manual["account_name"] == "自定义科目"
    assert manual["account_kept"] == {"account_name": "自定义科目", "template_account_name": "营业收入和营业成本"}
    assert _plan("营业收入与营业成本", None)["account_name"] is None  # 不补


def test_target_template_account_name_wins_when_it_differs_from_its_title():
    target = {**TGT, "account_name": "营业收入"}
    out = _plan("营业收入与营业成本", "营业收入与营业成本", target=target)
    assert out["account_name"] == "营业收入"


def test_no_target_title_changes_nothing():
    out = _plan("营业收入与营业成本", "营业收入与营业成本", target_title="")
    assert (out["section_title"], out["account_name"], out["title_kept"], out["account_kept"]) == (
        "营业收入与营业成本", "营业收入与营业成本", None, None)


def test_revert_only_when_current_value_is_still_a_system_value():
    snap = {"section_title": "营业收入与营业成本", "account_name": "营业收入与营业成本"}
    back = revert_title_fields("营业收入和营业成本", "营业收入和营业成本", snap, TGT)
    assert (back["section_title"], back["account_name"], back["kept"]) == (
        "营业收入与营业成本", "营业收入与营业成本", [])
    kept = revert_title_fields("转换后审计师改的标题", "营业收入和营业成本", snap, TGT)
    assert kept["section_title"] == "转换后审计师改的标题" and kept["account_name"] == "营业收入与营业成本"
    assert kept["kept"] == [{"field": "section_title", "current": "转换后审计师改的标题",
                             "snapshot": "营业收入与营业成本"}]
    # 本修复之前的 v2 快照没有这两个键（那时转换不改标题）⇒ 不动
    legacy = revert_title_fields("营业收入和营业成本", None, {}, TGT)
    assert legacy["section_title"] == "营业收入和营业成本" and legacy["kept"] == []


@pytest.fixture(scope="module")
def fx() -> _Fx:
    return _Fx()


def _bridged_note(fx: _Fx, *, title: str | None = None, account: str | None = None):
    note = make_note(section_id=fx.bridged["source_sid"], note_section=fx.bridged_src_num,
                     section_title=title if title is not None else fx.bridged["source_title"])
    note.account_name = account
    return note


async def test_conversion_keeps_manual_title_and_reports_it(fx: _Fx):
    note = _bridged_note(fx, title="审计师改过的标题", account="审计师改过的科目")
    result = await _forward(ConversionSession([note]))
    assert note.section_id == fx.bridged["target_sid"] and note.note_section == fx.bridged_tgt_num
    assert (note.section_title, note.account_name) == ("审计师改过的标题", "审计师改过的科目")
    detail = result["notes_detail"]
    assert detail["titles_kept"] == [{
        "note_id": str(note.id), "note_section": fx.bridged_tgt_num, "title": "审计师改过的标题",
        "template_title": fx.listed[fx.bridged["target_sid"]]["section_title"],
    }]
    assert [k["account_name"] for k in detail["account_names_kept"]] == ["审计师改过的科目"]
    assert any("人工改过" in w for w in result["warnings"])


async def test_round_trip_restores_system_title_but_keeps_later_manual_edit(fx: _Fx):
    target_title = fx.listed[fx.bridged["target_sid"]]["section_title"]
    assert target_title != fx.bridged["source_title"], "判据失效：别名桥接两侧标题相同"

    note = _bridged_note(fx, account=fx.bridged["source_title"])
    sess = ConversionSession([note])
    await _forward(sess)
    assert note.section_title == target_title and note.account_name == target_title
    rolled = await _rollback(sess)
    assert rolled["status"] == "rolled_back", rolled["sections"]
    assert note.section_title == note.account_name == fx.bridged["source_title"]

    edited = _bridged_note(fx)
    sess = ConversionSession([edited])
    await _forward(sess)
    edited.section_title = "转换后审计师改的标题"
    rolled = await _rollback(sess)
    assert edited.section_title == "转换后审计师改的标题" and edited.section_id == fx.bridged["source_sid"]
    assert rolled["status"] == "partial"
    assert [k["field"] for k in rolled["sections"]["titles_kept"]] == ["section_title"]


async def test_preview_lists_kept_titles_without_writing(fx: _Fx):
    note = _bridged_note(fx, title="审计师改过的标题")
    preview = await NoteConversionService(ConversionSession([note])).preview_note_conversion(PROJECT, YEAR, "listed")
    assert [k["title"] for k in preview["details"]["titles_kept"]] == ["审计师改过的标题"]
    assert note.section_id == fx.bridged["source_sid"] and note.section_title == "审计师改过的标题"
