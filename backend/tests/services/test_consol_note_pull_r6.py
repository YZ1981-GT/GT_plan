"""合并附注拉数的行明细对应（spec note-table-structure-formula-pull-closure R6）。纯函数 + 真模板，无 DB。

判据：①行名比较键去「【…】」编制提示 / 可选行方括号、括号统一全角 ②单体账龄档落在合并某一档里 ⇒ 并到那一档（可自动确认），
建议模板不另起一行 ③通用别名（上年年末余额 ≡ 期初余额 …）双向，且「上一行按别名配上」不再让下一行建议丢失 ④同名行分组按
通用别名归一 ⑤来源合计 / 小计行不模糊配：模板唯一合计行 ⇒ total_row，模板没有 ⇒ 建议忽略 ⑥国企单体「小计 / 减：坏账准备 /
合计」折进合并「合计」行的账面余额 + 坏账准备列 ⑦来源独有行按来源位置放 ⑧金额列一列都没对上要报原因 ⑨自动映射按忽略提交。
"""
from __future__ import annotations

import math

import pytest

from app.services.consol_note_detail_order import place_source_rows
from app.services.consol_note_detail_suggest import (
    TOTAL_IGNORED,
    _label_key,
    is_auto_confirmable,
    suggest_template_rows,
)
from app.services.note_aging_buckets import bucket_interval, containing_bucket


def _tpl(*rows: tuple[str, str]) -> list[dict]:
    return [{"target_row_id": f"t{i}", "canonical_name": name, "aliases": [], "row_type": rt}
            for i, (name, rt) in enumerate(rows)]


def _src(*rows, groups=None) -> list[dict]:
    out = []
    for i, r in enumerate(rows):
        label, rt = (r, "data") if isinstance(r, str) else r
        item = {"label": label, "row_type": rt}
        if groups:
            item["group"], item["group_occurrence"] = groups[i]
        out.append(item)
    return [{"source_rows": out}]


def _by_label(result: list[dict]) -> dict[str, dict]:
    return {s["source_label"]: s for s in result}


# ── ① 行名比较键 ──

@pytest.mark.parametrize("a,b", [
    ("按组合计提坏账准备【注意：与会计政策中披露的组合保持一致】", "按组合计提坏账准备"),
    ("[本期转销]", "本期转销"),
    ("［其他］", "其他"),
    ("其中：尚未开发的土地储备(由房地产开发企业填列）", "其中：尚未开发的土地储备（由房地产开发企业填列）"),
    ("1-2年", "1至2年"),
])
def test_label_key_treats_hint_and_optional_brackets_as_same_row(a, b):
    assert _label_key(a) == _label_key(b)


def test_label_key_keeps_label_that_is_only_a_hint():
    assert _label_key("【负数】") == "【负数】"


# ── ② 账龄档包含 ──

def test_bucket_interval_reads_digit_buckets_only():
    assert bucket_interval("1年以内（含1年）") == (0.0, 365.0)
    assert bucket_interval("1至2年") == (365.0, 730.0)
    assert bucket_interval("3 年以上") == (1095.0, math.inf)
    assert bucket_interval("0-6个月") == (0.0, 180.0)
    for label in ("一年以内", "其中：0-X个月", "1年以内小计：", "合计", "3至3年"):
        assert bucket_interval(label) is None, label


def test_containing_bucket_takes_narrowest_and_refuses_ties():
    soe = ["1年以内（含1年）", "1至2年", "2至3年", "3年以上", "合  计"]
    assert [containing_bucket(x, soe) for x in ("3至4年", "4-5年", "5年以上", "1年以内")] == [3, 3, 3, 0]
    assert containing_bucket("0-6个月", ["1年以内", "其中：0-6个月", "0-6个月"]) == 2
    assert containing_bucket("6年以上", ["3年以上", "5年以上"]) == 1, "同宽取下限高的"
    assert containing_bucket("2至4年", soe) is None, "跨档：不并"
    assert containing_bucket("3年以上", ["3至4年", "4至5年", "5年以上"]) is None, "粗档拆不开"


def test_aging_rows_fold_into_the_containing_template_bucket():
    tpl = _tpl(("1年以内（含1年）", "data"), ("1至2年", "data"), ("2至3年", "data"), ("3年以上", "data"),
               ("合  计", "total"))
    got = _by_label(suggest_template_rows(
        _src("1年以内", "1至2年", "2至3年", "3至4年", "4至5年", "5年以上", ("合 计", "total")),
        existing_template_rows=tpl))
    assert {k: (v["match_type"], v["suggested_target"]["target_row_id"]) for k, v in got.items()} == {
        "1年以内": ("aging_bucket", "t0"), "1至2年": ("exact", "t1"), "2至3年": ("exact", "t2"),
        "3至4年": ("aging_bucket", "t3"), "4至5年": ("aging_bucket", "t3"), "5年以上": ("aging_bucket", "t3"),
        "合 计": ("exact", "t4")}
    assert all(is_auto_confirmable(s) for s in got.values())


# ── ③ 通用别名 ──

def test_global_aliases_for_opening_and_closing_rows_both_directions():
    got = _by_label(suggest_template_rows(_src("上年年末余额", "本期计提", "期末数"),
                                          existing_template_rows=_tpl(("期初余额", "data"), ("本期计提", "data"),
                                                                      ("期末余额", "data"))))
    assert (got["上年年末余额"]["match_type"], got["上年年末余额"]["suggested_target"]["target_row_id"]) == ("global_alias", "t0")
    assert got["期末数"]["suggested_target"]["target_row_id"] == "t2"
    back = suggest_template_rows(_src("期初余额"), existing_template_rows=_tpl(("上年年末余额", "data")))
    assert back[0]["match_type"] == "global_alias" and back[0]["suggested_target"]["target_row_id"] == "t0"


def test_row_after_a_global_alias_match_is_not_dropped():
    """原先：上一行按通用别名配上、这一行是别名库里的标准名却反查不到 ⇒ 这一行整条建议丢失（不出现在弹窗里）。"""
    result = suggest_template_rows(_src("现金", "期初余额"), existing_template_rows=_tpl(("库存现金", "data")))
    assert [s["source_label"] for s in result] == ["现金", "期初余额"]
    assert result[1]["match_type"] == "manual"


# ── ④ 同名行分组按别名归一 ──

def test_repeated_rows_under_alias_equivalent_heads_pair_by_group():
    tpl = _tpl(("按单项计提坏账准备", "data"), ("其中：", "data"), ("按组合计提坏账准备", "data"), ("其中：", "data"),
               ("合计", "total"))
    from app.services.consol_note_row_groups import row_groups

    labels = ["按单项计提减值准备", "其中：", "按组合计提减值准备", "其中：", "合计"]
    groups = row_groups(labels, ["data", "data", "data", "data", "total"])
    result = suggest_template_rows(_src(*labels[:4], ("合计", "total"), groups=groups), existing_template_rows=tpl)
    members = [s for s in result if s["source_label"] == "其中："]
    assert [(s["match_type"], s["suggested_target"]["target_row_id"]) for s in members] == [("exact", "t1"), ("exact", "t3")]


# ── ⑤ 合计 / 小计行 ──

def test_source_totals_never_fuzzy_match_and_missing_ones_are_ignored():
    tpl = _tpl(("1年以内", "data"), ("合  计", "total"))
    got = _by_label(suggest_template_rows(_src("1年以内", ("小  计", "subtotal"), ("总计", "total")),
                                          existing_template_rows=tpl))
    assert got["小  计"]["match_type"] == TOTAL_IGNORED and got["小  计"]["mapping_action"] == "ignore"
    assert got["小  计"]["ignore_reason"] and is_auto_confirmable(got["小  计"])
    assert (got["总计"]["match_type"], got["总计"]["suggested_target"]["target_row_id"]) == ("total_row", "t1")
    none = suggest_template_rows(_src(("合计", "total")), existing_template_rows=_tpl(("A", "data")))
    assert none[0]["match_type"] == TOTAL_IGNORED


# ── ⑥ 国企账龄表：小计 / 减：坏账准备 / 合计 折进合并合计行 ──

def _read_soe_aging(consol_id: str, standalone_no: str, table_name: str):
    from app.services.consol_note_formula_service import find_table
    from app.services.consol_note_standalone_reader import read_source_table
    from app.services.note_table_header_catalog import standalone_sections

    consol = find_table("soe", consol_id)
    tables = dict(standalone_sections("soe"))[standalone_no]
    single = next(t for t in tables if t.get("name") == table_name)
    rows = []
    for i, r in enumerate(single["rows"]):
        row = dict(r) if isinstance(r, dict) else {"label": r[0]}
        row["values"] = [float(100 * (i + 1) + c) for c in range(1, len(single["headers"]))]
        rows.append(row)
    td = {"_tables": [{**t, "rows": rows} if t is single else t for t in tables]}
    return read_source_table(td, consol_table=consol, table_name=table_name, title=consol.get("title"),
                             section_title="应收账款", std="soe", consol_section_id=consol_id,
                             standalone_section=standalone_no)


def test_soe_aging_subtotal_and_provision_rows_fold_into_total():
    src = _read_soe_aging("五-5-1", "八、5", "（1）按账龄披露应收账款")
    labels = [r["label"] for r in src.rows]
    assert "减：坏账准备" not in labels and "小 计" not in labels
    assert src.folded_rows == ["小 计", "减：坏账准备"] and src.to_status()["folded_rows"] == src.folded_rows
    total = next(r for r in src.rows if r["row_type"] == "total")
    # 合并列：期末数·账面余额 / 期末数·坏账准备 / 期初数·账面余额 / 期初数·坏账准备；单体第 7 行小计、第 8 行减：坏账准备
    assert total["values"] == [701.0, 801.0, 702.0, 802.0]
    assert src.reason is None


def test_fold_only_when_template_lacks_the_row_and_has_an_unmatched_provision_column():
    from app.services.consol_note_provision_fold import fold_provision_rows
    from app.services.note_table_header_library import ColumnKey

    gross = ColumnKey(1, ("期末余额", "账面余额"), "end", ("账面余额",), "amount")
    provision = ColumnKey(2, ("期末余额", "坏账准备"), "end", ("坏账准备",), "amount")
    keys = [ColumnKey(0, ("账龄",), None, (), "label"), gross, provision]
    rows = [{"label": "1年以内", "row_type": "data", "values": [1.0, None]},
            {"label": "减：坏账准备", "row_type": "data", "values": [2.0, None]},
            {"label": "合计", "row_type": "total", "values": [3.0, None]}]
    assert fold_provision_rows(rows, keys, [1], ["1年以内", "减：坏账准备", "合计"]) == (rows, []), "模板有这一行：照常对行"
    assert fold_provision_rows(rows, keys[:2], [1], ["1年以内", "合计"]) == (rows, []), "没有坏账准备列：不折"
    assert fold_provision_rows(rows, keys, [1, 2], ["1年以内", "合计"]) == (rows, []), "坏账准备列对上了来源列：不折"
    # ADR-14 / R17.3：缺紧邻小计时不折叠——没有可靠的账面余额合计，折了会让净额留在账面余额列
    assert fold_provision_rows(rows, keys, [1], ["1年以内", "合计"]) == (rows, []), "没有小计行：不折叠（宁缺勿错）"


def test_built_consol_total_takes_folded_provision_and_recomputes_gross():
    """apply 按本表重算：账面余额列 = 各账龄档之和；坏账准备列各档为空 ⇒ 取来源合计（折进来的减：坏账准备）。"""
    from app.services.consol_note_formula_service import find_table
    from app.services.consol_note_table_totals import build_note_rows
    from decimal import Decimal

    consol = find_table("soe", "五-5-1")
    skeleton = [(r[0], rt) for r, rt in zip(consol["rows"], consol["_row_types"])]
    amounts = {0: {1: Decimal("100"), 3: Decimal("90")}, 3: {1: Decimal("40"), 3: Decimal("30")},
               4: {1: Decimal("999"), 2: Decimal("12"), 3: Decimal("999"), 4: Decimal("8")}}
    built = build_note_rows(skeleton, amounts, width=5, protected=set(), existing_rows=[], table=consol)
    assert built.rows[4][1:] == ["140.00", "12.00", "120.00", "8.00"]


# ── ⑦ 来源独有行放在来源里的位置 ──

def _sk(*rows):
    return [{"canonical_name": n, "_key": _label_key(n), "row_type": rt, **({"category": "dynamic_zone"} if n == "……" else {})}
            for n, rt in rows]


def _ex(*names):
    return [{"canonical_name": n, "_key": _label_key(n), "row_type": "data"} for n in names]


def test_source_only_rows_follow_their_source_anchor_not_the_first_total():
    skeleton = _sk(("按单项计提坏账准备", "data"), ("其中：", "data"), ("按组合计提坏账准备", "data"), ("其中：", "data"),
                   ("应收中央企业客户", "data"), ("合计", "total"))
    seq = [_label_key(x) for x in ("按单项计提坏账准备", "其中：", "单位A", "单位B", "按组合计提坏账准备", "其中：",
                                   "账龄组合", "合计")]
    got = [r["canonical_name"] for r in place_source_rows(skeleton, _ex("单位A", "单位B", "账龄组合"), [seq])]
    assert got == ["按单项计提坏账准备", "其中：", "单位A", "单位B", "按组合计提坏账准备", "其中：", "账龄组合",
                   "应收中央企业客户", "合计"]


def test_source_only_rows_replace_following_placeholder_and_loose_rows_keep_old_rule():
    skeleton = _sk(("1年以内", "data"), ("1至2年", "data"), ("……", "data"), ("合计", "total"))
    seq = [_label_key(x) for x in ("1年以内", "1-2年", "2-3年", "3-4年", "合计")]
    got = [r["canonical_name"] for r in place_source_rows(skeleton, _ex("2-3年", "3-4年"), [seq])]
    assert got == ["1年以内", "1至2年", "2-3年", "3-4年", "合计"]
    loose = place_source_rows(skeleton, _ex("X"), [[_label_key("X"), _label_key("1年以内")]])
    assert [r["canonical_name"] for r in loose] == ["1年以内", "1至2年", "X", "合计"], "前面没有模板行：替换「……」"


def test_merged_rows_anchor_source_only_rows():
    skeleton = _sk(("库存现金", "data"), ("银行存款", "data"), ("合计", "total"))
    seq = [_label_key(x) for x in ("现金", "备用金", "银行存款", "合计")]
    got = place_source_rows(skeleton, _ex("备用金"), [seq], merged={_label_key("现金"): _label_key("库存现金")})
    assert [r["canonical_name"] for r in got] == ["库存现金", "备用金", "银行存款", "合计"]


def test_grouped_table_gets_one_source_only_row_per_group_and_pairs_by_group():
    """国企无形资产：各组都有单体独有的「住房使用权」，单体写「其中：土地使用权」而合并写「土地使用权」。
    原先独有行只建一行、别名只加在第一组的同名行上 ⇒ 后几组只能按位置配（须人工确认、还配到第一组的行）。"""
    from app.services.consol_note_detail_order import suggest_detail_rows
    from app.services.consol_note_row_groups import row_groups

    heads = ("一、原价合计", "二、累计摊销合计")
    table = {"rows": [[h] for g in heads for h in (g, "土地使用权", "专利权")] + [["合计"]],
             "_row_types": ["data"] * 6 + ["total"]}
    labels = [label for g in heads for label in (g, "其中：土地使用权", "住房使用权", "专利权")]
    rows = suggest_detail_rows(table, [[{"label": label, "row_type": "data", "values": [1.0]} for label in labels]])
    assert [r["canonical_name"] for r in rows] == [
        "一、原价合计", "土地使用权", "住房使用权", "专利权",
        "二、累计摊销合计", "土地使用权", "住房使用权", "专利权", "合计"]
    assert [r["aliases"] for r in rows if r["canonical_name"] == "土地使用权"] == [["其中：土地使用权"]] * 2

    tpl = [{**r, "target_row_id": f"r{i}"} for i, r in enumerate(rows)]
    groups = row_groups(labels, ["data"] * len(labels))
    got = suggest_template_rows(_src(*labels, groups=groups), existing_template_rows=tpl)
    pairs = [(s["source_label"], s.get("source_group", ""), s["match_type"], s["suggested_target"]["target_row_id"])
             for s in got if s["source_label"] in ("其中：土地使用权", "住房使用权")]
    assert pairs == [
        ("其中：土地使用权", "一、原价合计", "alias", "r1"), ("其中：土地使用权", "二、累计摊销合计", "alias", "r5"),
        ("住房使用权", "一、原价合计", "exact", "r2"), ("住房使用权", "二、累计摊销合计", "exact", "r6")]


# ── ⑧ 金额列一列都没对上 ──

def test_reader_reports_reason_when_no_amount_column_matches():
    from app.services.consol_note_standalone_reader import read_source_table

    # 真实形态：跨口径的固定资产表（合并按期间分列、单体按资产类别分列，一列都对不上）
    consol = {"title": "X", "headers": ["项目", "期初余额", "期末余额"], "rows": [["A", "", ""]]}
    td = {"_tables": [{"name": "X", "headers": ["项目", "房屋及建筑物", "机器设备"],
                       "rows": [{"label": "A", "values": [1, 2]}]}]}
    src = read_source_table(td, consol_table=consol, table_name="X", title="X", std="soe")
    assert src.rows and src.reason and "一列都没对上" in src.reason
    # R15 / ADR-11：金额列全未匹配必须是 unreadable，不能参与映射和 apply
    assert src.to_status()["status"] == "unreadable"
    assert not src.usable


# ── ⑨ 自动映射按忽略提交 ──

def test_auto_mapping_submits_ignored_totals_with_reason():
    from app.services.consol_note_auto_mapping import _auto_mapping

    ignored = suggest_template_rows(_src(("小计", "subtotal")), existing_template_rows=_tpl(("A", "data")))[0]
    entry = _auto_mapping(("小计",), ignored)
    assert entry["mapping_action"] == "ignore" and entry["ignore_reason"] and entry["target_row_id"] == ""
    mapped = _auto_mapping(("A",), suggest_template_rows(_src("A"), existing_template_rows=_tpl(("A", "data")))[0])
    assert mapped == {"source_label": "A", "target_row_id": "t0", "mapping_action": "map"}
