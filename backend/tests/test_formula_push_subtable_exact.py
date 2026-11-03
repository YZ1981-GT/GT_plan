"""子表推送规则只按精确表名定位、缺值键不崩（spec note-pull-followup-closure R2.3）。

原实现三处会把数写错地方 / 让整张底稿回滚：
- 旧格式附注（``_tables``）表名对不上回退首表（``_pick_table``）—— 子表规则把科目合计写进主表；
- 章节标题不符时按规则表名反查同前缀章节、改投到别的章节；
- 取数行没有该字段的值键（子表字段「坏账准备」「比例」…）时 ``row[f"{vk}_resolved"]`` KeyError。
"""
from __future__ import annotations

import asyncio
from unittest.mock import patch

from app.services.formula_push import engine as engine_mod
from app.services.formula_push.note_writer import has_table, locate_table
from tests.test_formula_push_note_skip import (
    _make_binding,
    _make_ctx,
    _make_note_mock,
    _make_paper,
    _make_rule,
    _make_sources,
    _setup_db_for_single_note,
)

_LEGACY = {
    "_tables": [
        {"name": "短期借款", "headers": ["项目", "期末余额", "上年年末余额"],
         "rows": [{"label": "短期借款", "values": [None, None]}, {"label": "合计", "values": [None, None], "is_total": True}]},
        {"name": "短期借款分类", "headers": ["项目", "期末余额", "上年年末余额"],
         "rows": [{"label": "信用借款", "values": [None, None]}, {"label": "合计", "values": [None, None], "is_total": True}]},
    ],
    "rows": [{"label": "短期借款", "values": [None, None]}, {"label": "合计", "values": [None, None], "is_total": True}],
}


def test_locate_exact_does_not_fall_back_to_first_table() -> None:
    table, reason = locate_table(_LEGACY, "短期借款分类", exact=True)
    assert table is not None and [r["label"] for r in table.rows] == ["信用借款", "合计"]
    table, reason = locate_table(_LEGACY, "已逾期未偿还的短期借款情况", exact=True)
    assert table is None and reason == "附注中没有「已逾期未偿还的短期借款情况」表"
    # 主表规则照旧：表名对不上写首表（= 顶层镜像那张）
    table, _ = locate_table(_LEGACY, "已逾期未偿还的短期借款情况")
    assert [r["label"] for r in table.rows] == ["短期借款", "合计"]
    single = {"name": "短期借款", "rows": [{"label": "短期借款", "values": [1, 2]}]}
    assert locate_table(single, "短期借款分类", exact=True)[0] is None
    assert locate_table(single, "短期借款", exact=True)[0] is not None


def test_has_table_shapes() -> None:
    assert has_table(_LEGACY, "短期借款分类") and has_table(_LEGACY, " 短期借款分类 ")
    assert not has_table(_LEGACY, "逾期借款")
    sub = {"sub_table_data": {"（1）按账龄披露应收账款": []}, "_tables": [{"name": "别的表", "rows": []}]}
    assert has_table(sub, "（1）按账龄披露应收账款") and not has_table(sub, "别的表")
    assert not has_table(None, "x") and not has_table({"rows": []}, "")


def _run(rule, note, rows, *, prefixes=("2001",)):
    db = _setup_db_for_single_note(note)
    ctx = _make_ctx(db=db)
    binding = _make_binding(rows, account_prefixes=prefixes)
    with patch.object(engine_mod, "_push_note_cell", return_value=True) as cell, \
         patch.object(engine_mod, "_push_note_total", return_value=False):
        section = asyncio.run(engine_mod._push_note(ctx, rule=rule, binding=binding, overlay={},
                                                    sources=_make_sources("soe"), paper=_make_paper()))
    return section, ctx, cell, db


_TB_ROWS = [{"note_label": "短期借款", "label": "短期借款", "ending": 300.0, "ending_resolved": True,
             "opening": 200.0, "opening_resolved": True, "is_total": False, "is_memo": False}]


def test_subtable_rule_writes_the_named_table_not_the_first() -> None:
    rule = _make_rule(rule_id="L1.note.subtable_0", table="短期借款分类", sections={"soe": "八、33"},
                      fields=("end_amount",))
    note = _make_note_mock(note_section="八、33", section_title="短期借款", table_data=_LEGACY)
    section, ctx, cell, _db = _run(rule, note, _TB_ROWS)
    assert section == "八、33"
    rows_written = [c.kwargs["row"]["label"] for c in cell.call_args_list]
    assert rows_written == ["合计"], "取数行对不上明细行 ⇒ 合计行兜底写的是「短期借款分类」的合计行"
    assert cell.call_args_list[0].kwargs["table"].rows[0]["label"] == "信用借款"


def test_subtable_rule_missing_table_skips_without_retarget_or_skeleton() -> None:
    rule = _make_rule(rule_id="L1.note.subtable_1", table="已逾期未偿还的短期借款情况", sections={"soe": "八、33"},
                      fields=("end_amount",))
    note = _make_note_mock(note_section="八、33", section_title="短期借款", table_data=_LEGACY)
    section, ctx, cell, db = _run(rule, note, _TB_ROWS)
    assert section is None and cell.call_count == 0
    reasons = [i.reason for i in ctx.result.items]
    assert reasons == ["附注 八、33「短期借款」里没有「已逾期未偿还的短期借款情况」表（子表规则只按表名精确定位），未推送"]
    assert db.execute.call_count == 1, "不按章节标题反查别的章节（原实现会再查一次同前缀章节）"
    assert "sub_table_data" not in note.table_data, "子表规则缺表不建骨架"


def test_missing_value_key_is_a_skip_not_a_keyerror() -> None:
    """取数行对上了附注行、但没有字段的值键（子表字段由披露同步写，不由取数）⇒ 跳过并说明，不抛 KeyError。"""
    rule = _make_rule(rule_id="L1.note.subtable_0", table="短期借款分类", sections={"soe": "八、33"},
                      fields=("end_amount", "provision"))
    data = {"_tables": [dict(_LEGACY["_tables"][1], rows=[{"label": "短期借款", "values": [None, None]},
                                                          {"label": "合计", "values": [None, None], "is_total": True}])]}
    note = _make_note_mock(note_section="八、33", section_title="短期借款", table_data=data)
    section, ctx, cell, _db = _run(rule, note, _TB_ROWS)
    assert section == "八、33" and cell.call_count == 1
    skipped = [i.reason for i in ctx.result.items if i.action == "skipped"]
    assert skipped == ["取数行没有「provision」的值（本底稿取数只有期末 / 期初数），附注保持原值"]


def test_main_rule_keeps_title_retarget() -> None:
    """主表规则的章节号动态定位照旧（只收窄子表规则）。"""
    rule = _make_rule(rule_id="L1.note.main", table="短期借款", sections={"soe": "八、32"})
    note = _make_note_mock(note_section="八、32", section_title="交易性金融负债", table_data=_LEGACY)
    _section, _ctx, _cell, db = _run(rule, note, _TB_ROWS)
    assert db.execute.call_count == 2, "主表规则标题不符 ⇒ 再查一次同前缀、标题等于表名的章节"
