"""四表库共享件 `aux_aggregation`：提升零回归守卫.

`pick_aux_type` 原在 `_f1_import_export`（平台唯一正确实现，G7 直接 import 它），
本 spec 提升为共享件后必须**语义逐字不变**。

spec: .kiro/specs/k1-extraction-chain-and-note-alignment/
Requirements 11.5 / Property 12
"""
from __future__ import annotations

import sqlalchemy as sa

from app.services.four_table.aux_aggregation import (
    AUX_TYPE_PREFERRED_KEYWORDS,
    AuxEntry,
    _prefix_predicate,
    pick_aux_type,
)


def test_reexport_from_f1_is_same_object():
    """F1 / G7 的既有 import 路径必须拿到**同一个函数对象**（薄壳 re-export）。"""
    from app.routers.wp_render_strategies._f1_import_export import (
        _AUX_TYPE_PREFERRED_KEYWORDS as f1_kw,
        pick_aux_type as f1_pick,
    )

    assert f1_pick is pick_aux_type
    assert f1_kw is AUX_TYPE_PREFERRED_KEYWORDS


def test_empty_candidates_return_none():
    assert pick_aux_type([]) is None


def test_preferred_keyword_wins_over_larger_amount():
    """含往来单位关键词的维度优先，即便金额更小（提升前后同款行为）。"""
    got = pick_aux_type([("成本中心", 9999, 1e9), ("客户", 3, 1.0)])
    assert got == "客户"


def test_among_preferred_larger_amount_wins():
    got = pick_aux_type([("客户", 10, 100.0), ("职员", 10, 200.0)])
    assert got == "职员"


def test_amount_negative_uses_absolute():
    got = pick_aux_type([("客户", 1, -500.0), ("供应商", 1, 100.0)])
    assert got == "客户"


def test_falls_back_to_all_when_no_preferred():
    got = pick_aux_type([("成本中心", 1, 10.0), ("保证金类别", 1, 50.0)])
    assert got == "保证金类别"


def test_row_count_breaks_amount_tie():
    got = pick_aux_type([("客户", 2, 100.0), ("职员", 7, 100.0)])
    assert got == "职员"


def test_none_and_blank_types_tolerated():
    assert pick_aux_type([(None, 0, 0.0)]) == ""
    assert pick_aux_type([("", None, None)]) == ""


def test_preferred_keywords_cover_real_aux_types_seen_in_db():
    """实测 1221 的 aux_type：客户 / 成本中心 / 保证金类别 / 职员 / 经营类往来款。
    其中「客户」「职员」「经营类往来款」应被识别为往来单位维度。"""
    preferred = [
        t for t in ("客户", "成本中心", "保证金类别", "职员", "经营类往来款")
        if any(kw in t for kw in AUX_TYPE_PREFERRED_KEYWORDS)
    ]
    assert set(preferred) == {"客户", "职员", "经营类往来款"}


def test_prefix_predicate_empty_is_false():
    assert str(_prefix_predicate(sa.column("account_code"), [])) == "false"
    assert str(_prefix_predicate(sa.column("account_code"), ["  ", ""])) == "false"


def test_prefix_predicate_builds_like_or():
    sql = str(_prefix_predicate(sa.column("account_code"), ["1221", "1231.03"]))
    assert sql.count("LIKE") == 2
    assert " OR " in sql


def test_aux_entry_is_positionally_compatible_with_f1_builder():
    """`AuxEntry` 顺序必须与 F1 的位置化元组一致（F1 builder 按位置解构）。"""
    e = AuxEntry("甲", 1.0, 2.0, 3.0, 4.0)
    assert (e[0], e[1], e[2], e[3], e[4]) == ("甲", 1.0, 2.0, 3.0, 4.0)
    assert e._fields == ("aux_name", "opening", "debit", "credit", "closing")
