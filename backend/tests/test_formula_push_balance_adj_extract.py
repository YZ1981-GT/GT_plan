"""审定表族审定合计来源求值的边界（纯函数）。spec formula-fetch-followup-defect-closure R6.3。"""
from __future__ import annotations

import json

import pytest

from app.services.formula_push.bindings.balance_adj_extract import (
    AUDITED_SOURCES,
    END_UNADJ_ADJ,
    U_AJE_RJE,
    ByMode,
    Key,
    RowList,
    Rows,
    Unavailable,
    conclusion_keys,
    evaluate,
)


def _rows(*rows: dict) -> str:
    return json.dumps(list(rows), ensure_ascii=False)


H1 = AUDITED_SOURCES["H1"]


def test_missing_or_empty_primary_list_is_unknown_not_zero():
    """主清单没存 / 空数组 / 不是数组 / 坏 JSON ⇒ None（派生目标写空），不当成 0。"""
    for entries in ({}, {"H1-1-cost-rows": ""}, {"H1-1-cost-rows": "[]"}, {"H1-1-cost-rows": "{}"},
                    {"H1-1-cost-rows": "not json"}):
        assert evaluate(H1, "receivable", entries, {}) is None, entries
        assert evaluate(H1, "net", entries, {}) is None, entries


def test_contra_lists_subtract_and_missing_contra_counts_as_zero():
    entries = {
        "H1-1-cost-rows": _rows({"category": "房屋", "unadjusted": 1000, "aje": 10, "rje": "5"}),
        "H1-1-dep-rows": _rows({"category": "房屋", "unadjusted": 300, "aje": "-20", "rje": None}),
    }
    assert evaluate(H1, "receivable", entries, {}) == 1015.0
    assert evaluate(H1, "net", entries, {}) == 735.0  # 1015 − 280；减值清单没存 ⇒ 0


def test_subtotal_and_total_rows_are_skipped():
    entries = {"H1-1-cost-rows": _rows(
        {"category": "房屋", "unadjusted": 100},
        {"category": "小计", "unadjusted": 100},
        {"category": "合计", "unadjusted": 100},
        {"category": "机器", "unadjusted": 50, "isSubtotal": True},
        {"category": "运输", "unadjusted": 50, "isTotal": True},
        "not a row",
    )}
    assert evaluate(H1, "receivable", entries, {}) == 100.0


def test_amount_field_groups_fall_back_from_new_to_legacy_shape():
    src = Rows((RowList("X-rows"),), (END_UNADJ_ADJ, U_AJE_RJE))
    entries = {"X-rows": _rows(
        {"name": "新", "endUnadjusted": 100, "endAdjustment": 5, "unadjusted": 999},
        {"name": "旧", "unadjusted": 20, "aje": 1, "rje": 1},
        {"name": "空"},
    )}
    totals = AUDITED_SOURCES["H2"].__class__(receivable=src, net=src, origin="t")
    assert evaluate(totals, "net", entries, {}) == 127.0


def test_section_filter_with_default():
    """H4：一个数组两段；没写 section 的行按原值段（与前端 _normalizeRow 一致）。"""
    h4 = AUDITED_SOURCES["H4"]
    entries = {"H4-1-rows": _rows(
        {"name": "钢材", "section": "original", "endUnadjusted": 100, "endAdjustment": 0},
        {"name": "水泥", "endUnadjusted": 40, "endAdjustment": 0},
        {"name": "钢材", "section": "impairment", "endUnadjusted": 30, "endAdjustment": 0},
    )}
    assert evaluate(h4, "receivable", entries, {}) == 140.0
    assert evaluate(h4, "net", entries, {}) == 110.0


def test_alternate_keys_are_tried_in_order():
    i3 = AUDITED_SOURCES["I3"]
    entries = {"I3-adj-rows": "[]", "I3-1-adj-rows": _rows({"investee": "甲", "unadjusted": 80, "aje": 0, "rje": 0})}
    assert evaluate(i3, "net", entries, {}) == 80.0
    assert evaluate(i3, "receivable", entries, {}) is None  # 商誉没有审定原值


@pytest.mark.parametrize(("raw", "want"), [
    ("148500", 148500.0), ("  12.3456 ", 12.35), (0, 0.0), ("0", 0.0),
    (None, None), ("", None), ("   ", None), ("abc", None), ("nan", None), ("inf", None), (True, None),
])
def test_persisted_key_parsing(raw, want):
    h8 = AUDITED_SOURCES["H8"]
    assert evaluate(h8, "net", {"H8-1-net-audited": raw}, {}) == want


def test_conclusion_keys_read_from_conclusions_not_remark():
    g4 = AUDITED_SOURCES["G4"]
    assert conclusion_keys(g4) == ("G4-1-adjudicated-amount",)
    assert evaluate(g4, "net", {"G4-1-adjudicated-amount": "999"}, {}) is None  # remark 列同名键不算
    assert evaluate(g4, "net", {}, {"G4-1-adjudicated-amount": "880.5"}) == 880.5
    assert evaluate(g4, "receivable", {}, {"G4-1-adjudicated-amount": "880.5"}) is None


def test_h3_mode_switch():
    h3 = AUDITED_SOURCES["H3"]
    entries = {
        "H3-1-cost-original-rows": _rows({"category": "房屋", "unadjusted": 500, "aje": 0, "rje": 0}),
        "H3-1-cost-dep-rows": _rows({"category": "房屋", "unadjusted": 100, "aje": 0, "rje": 0}),
        "H3-1-fair-rows": _rows({"category": "房屋", "unadjusted": 700, "aje": 10, "rje": 0}),
    }
    assert (evaluate(h3, "receivable", entries, {}), evaluate(h3, "net", entries, {})) == (500.0, 400.0)
    fair = {**entries, "H3-measurement-model": "fair_value"}
    assert (evaluate(h3, "receivable", fair, {}), evaluate(h3, "net", fair, {})) == (710.0, 710.0)
    other = {**entries, "H3-measurement-model": "cost"}
    assert evaluate(h3, "net", other, {}) == 400.0


def test_unavailable_and_bad_kind():
    assert evaluate(AUDITED_SOURCES["G1"], "net", {"G1-1-rows": "{}"}, {"G1-1-adjudicated-amount": "1"}) is None
    with pytest.raises(ValueError):
        evaluate(H1, "baddebt", {}, {})
    assert isinstance(AUDITED_SOURCES["H7"].net, Unavailable)
    assert isinstance(AUDITED_SOURCES["K7"].net, Key) and isinstance(AUDITED_SOURCES["H3"].net, ByMode)
