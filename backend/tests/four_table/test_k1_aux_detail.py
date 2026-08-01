"""K1-2 明细表 ← 辅助余额归集：纯函数守卫.

spec: .kiro/specs/k1-extraction-chain-and-note-alignment/
Requirements 1.1~1.6 / Properties 1, 2
"""
from __future__ import annotations

import itertools
import re
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.four_table.aux_aggregation import AuxEntry
from app.services.four_table.k1_aux_detail import (
    K1_NATURE_FALLBACK,
    K1_NATURE_RULES,
    build_k1_detail_rows_from_aux,
    classify_k1_nature,
    classify_k1_nature_key,
    merge_k1_detail_rows,
)

REPO = Path(__file__).resolve().parents[3]
FRONTEND = REPO / "audit-platform" / "frontend" / "src" / "components" / "workpaper"


class _Seg:
    def __init__(self, key: str, label: str = ""):
        self.key = key
        self.label = label or key


FIVE = [_Seg(k) for k in ("within1", "y1to2", "y2to3", "y3to4", "y4to5", "over5")]
THREE = [_Seg(k) for k in ("within1", "y1to2", "over2")]


def _ids():
    c = itertools.count(1)
    return lambda: f"row-{next(c)}"


# ─────────────────── 性质分类：与前端 classifyK1Nature 同源 ───────────────────


@pytest.mark.parametrize(
    "name,expect_key,expect_label",
    [
        ("履约保证金", "margin", "保证金"),
        ("房租押金", "deposit", "押金"),
        ("员工备用金", "petty", "备用金"),
        ("关联方往来款", "intercompany", "往来款"),
        ("代垫费用", "intercompany", "往来款"),
        ("其他零星款", "other-nature", "其他"),
        ("", "other-nature", "其他"),
    ],
)
def test_classify_nature_key_and_label(name, expect_key, expect_label):
    assert classify_k1_nature_key(name) == expect_key
    assert classify_k1_nature(name) == expect_label


def test_nature_priority_margin_before_deposit():
    """源模板②行名是「保证金、押金」合并列示，但 K1-1 分两行 →
    含两词时必须优先「保证金」（与前端 classifyK1Nature 的判定顺序一致）。"""
    assert classify_k1_nature("投标保证金及押金") == "保证金"


def test_nature_rules_mirror_frontend_source():
    """🔴 反向自检：规则表必须与前端 `k1AdjudicationModel.classifyK1Nature` 逐条对应。

    前端是判定顺序 保证金 → 押金 → 备用金 → 往来|代垫|关联 → other-nature。
    抽前端源码正则并断言 key 序列一致（防两侧漂移出第二真源）。
    """
    src = (FRONTEND / "composables" / "k1AdjudicationModel.ts").read_text(encoding="utf-8")
    body = src.split("export function classifyK1Nature", 1)[1].split("\n}", 1)[0]
    keys = re.findall(r"return '([a-z-]+)'", body)
    assert keys, "前端 classifyK1Nature 抽取为空（正则失效）"
    expect = [k for _p, k, _l in K1_NATURE_RULES] + [K1_NATURE_FALLBACK[0]]
    assert keys == expect, f"前端 {keys} vs 共享件 {expect}"


# ─────────────────── 归集：字段名 / 关联方 / 账龄 / 截断 ───────────────────


def test_row_field_names_match_frontend_model():
    """🔴 字段名逐字对齐前端 `K1DetailRow` —— 特别是
    `beginBalance`/`endBalance`（后端导入导出曾错用 openingBalance/closingBalance）。"""
    rows = build_k1_detail_rows_from_aux(
        [AuxEntry("甲公司", 100.0, 50.0, 20.0, 130.0)], FIVE, row_id_factory=_ids()
    )
    assert len(rows) == 1
    r = rows[0]
    expected = {
        "id", "seq", "counterparty", "nature", "relatedParty",
        "beginBalance", "endBalance",
        "agingPrior", "agingCurrent", "agingAudited",
        "stage", "badDebtProvision", "netValue",
        "voucherNo", "conclusion", "remark",
    }
    assert set(r.keys()) == expected
    assert "openingBalance" not in r and "closingBalance" not in r
    assert r["beginBalance"] == 100.0
    assert r["endBalance"] == 130.0
    assert r["netValue"] == 130.0
    assert r["stage"] == 1


def test_related_party_flagged_from_registry():
    rows = build_k1_detail_rows_from_aux(
        [AuxEntry("甲公司", 0, 0, 0, 10.0), AuxEntry("乙公司", 0, 0, 0, 20.0)],
        FIVE,
        related_party_names=["甲公司", " "],
        row_id_factory=_ids(),
    )
    assert [r["relatedParty"] for r in rows] == ["是", "否"]


def test_nature_not_all_other():
    """F1 踩过的坑：归集行款项性质全落占位「其他」→ 让「带入未审数」把合计翻倍。"""
    rows = build_k1_detail_rows_from_aux(
        [
            AuxEntry("投标保证金-甲", 0, 0, 0, 1.0),
            AuxEntry("门店押金-乙", 0, 0, 0, 2.0),
            AuxEntry("备用金-丙", 0, 0, 0, 3.0),
            AuxEntry("某公司往来", 0, 0, 0, 4.0),
        ],
        FIVE,
        row_id_factory=_ids(),
    )
    assert [r["nature"] for r in rows] == ["保证金", "押金", "备用金", "往来款"]


def test_aging_buckets_follow_segments_and_land_first():
    for segs in (FIVE, THREE):
        rows = build_k1_detail_rows_from_aux(
            [AuxEntry("甲", 70.0, 0, 0, 100.0)], segs, row_id_factory=_ids()
        )
        r = rows[0]
        keys = [s.key for s in segs]
        for field in ("agingPrior", "agingCurrent", "agingAudited"):
            assert list(r[field].keys()) == keys, field
        assert r["agingCurrent"]["within1"] == 100.0
        assert r["agingPrior"]["within1"] == 70.0
        assert sum(r["agingCurrent"].values()) == 100.0


def test_empty_segments_fallback_within1():
    rows = build_k1_detail_rows_from_aux(
        [AuxEntry("甲", 0, 0, 0, 5.0)], [], row_id_factory=_ids()
    )
    assert list(rows[0]["agingCurrent"].keys()) == ["within1"]


def test_blank_names_skipped_and_row_limit():
    entries = [AuxEntry("", 0, 0, 0, 1.0), AuxEntry("  ", 0, 0, 0, 1.0)] + [
        AuxEntry(f"单位{i}", 0, 0, 0, float(i)) for i in range(10)
    ]
    rows = build_k1_detail_rows_from_aux(entries, FIVE, row_limit=5, row_id_factory=_ids())
    # row_limit 先截断再跳空名 → 截断后剩 5 项里含 2 个空名
    assert len(rows) == 3
    assert all(r["counterparty"] for r in rows)


def test_closing_falls_back_to_rollforward_when_absent():
    rows = build_k1_detail_rows_from_aux(
        [AuxEntry("甲", 100.0, 30.0, 10.0, 0.0)], FIVE, row_id_factory=_ids()
    )
    assert rows[0]["endBalance"] == 120.0


def test_source_hint_in_remark():
    rows = build_k1_detail_rows_from_aux(
        [AuxEntry("甲", 0, 0, 0, 1.0)], FIVE, row_id_factory=_ids(), source_hint="1221·客户"
    )
    assert rows[0]["remark"] == "由辅助余额表(1221·客户)导入"


# ─────────────────── Property 1：归集守恒 ───────────────────


@settings(max_examples=5, deadline=None)
@given(
    st.lists(
        st.tuples(
            st.text(alphabet="甲乙丙丁戊己庚辛", min_size=1, max_size=4),
            st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
            st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
        ),
        min_size=1,
        max_size=12,
        unique_by=lambda t: t[0],
    )
)
def test_property_aggregation_conserves_totals(items):
    entries = [AuxEntry(n, op, 0.0, 0.0, cl) for n, op, cl in items]
    rows = build_k1_detail_rows_from_aux(entries, FIVE, row_id_factory=_ids())
    exp_end = sum(round(e.closing if abs(e.closing) > 1e-9 else e.opening, 2) for e in entries)
    got_end = sum(r["endBalance"] for r in rows)
    assert abs(got_end - exp_end) < 0.05
    exp_begin = sum(round(e.opening, 2) for e in entries)
    assert abs(sum(r["beginBalance"] for r in rows) - exp_begin) < 0.05
    # 账龄桶之和 == 期末（整笔落首档）
    for r in rows:
        assert abs(sum(r["agingCurrent"].values()) - r["endBalance"]) < 0.005


# ─────────────────── Property 2：手工优先幂等 ───────────────────


def test_merge_skips_existing_counterparty_and_is_idempotent():
    existing = [
        {"id": "manual-1", "seq": 7, "counterparty": "甲公司", "endBalance": 999.0,
         "nature": "手工分类", "remark": "手工录入"},
    ]
    incoming = build_k1_detail_rows_from_aux(
        [AuxEntry("甲公司", 0, 0, 0, 1.0), AuxEntry("乙公司", 0, 0, 0, 2.0)],
        FIVE, row_id_factory=_ids(),
    )
    merged, added = merge_k1_detail_rows(existing, incoming)
    assert [r["counterparty"] for r in merged] == ["甲公司", "乙公司"]
    assert len(added) == 1
    # 手工行逐字不变
    assert merged[0] == existing[0]
    # seq 续编，不与既有撞号
    assert merged[1]["seq"] == 8

    incoming2 = build_k1_detail_rows_from_aux(
        [AuxEntry("甲公司", 0, 0, 0, 1.0), AuxEntry("乙公司", 0, 0, 0, 2.0)],
        FIVE, row_id_factory=_ids(),
    )
    merged2, added2 = merge_k1_detail_rows(merged, incoming2)
    assert added2 == []
    assert [r["counterparty"] for r in merged2] == ["甲公司", "乙公司"]


def test_merge_tolerates_none_and_garbage_existing():
    incoming = build_k1_detail_rows_from_aux(
        [AuxEntry("甲", 0, 0, 0, 1.0)], FIVE, row_id_factory=_ids()
    )
    for bad in (None, [], [None, "x", 1]):
        merged, added = merge_k1_detail_rows(bad, incoming)  # type: ignore[arg-type]
        assert len(added) == 1
        assert merged[-1]["counterparty"] == "甲"
