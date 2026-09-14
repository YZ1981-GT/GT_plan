"""K1-3 坏账准备明细 ← 备抵科目叶子 seed：纯函数守卫.

spec: .kiro/specs/k1-extraction-chain-and-note-alignment/
Requirements 2.1~2.5 / Property 3
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.four_table.k1_detail_seed import (
    K1_BAD_DEBT_ITEM_ID,
    build_k1_bad_debt_seed_from_tb,
    seed_k1_bad_debt,
)
from app.services.four_table.leaf_aggregation import LeafRow

REPO = Path(__file__).resolve().parents[3]
FRONTEND = REPO / "audit-platform" / "frontend" / "src" / "components" / "workpaper"

EPS = 0.005


def _leaf(code: str, opening=0.0, closing=0.0, debit=0.0, credit=0.0, name="坏账准备-其他应收款"):
    return LeafRow(
        account_code=code, account_name=name,
        opening=opening, closing=closing, debit=debit, credit=credit,
    )


def _row(payload: dict, category: str) -> dict:
    return next(r for r in payload["mainRows"] if r["category"] == category)


# ─────────────────── 基本映射 ───────────────────


def test_seed_maps_credit_to_provision_and_debit_to_reversal():
    leaves = [_leaf("1231.03", opening=1000.0, credit=300.0, debit=100.0, closing=1200.0)]
    p = build_k1_bad_debt_seed_from_tb(leaves, ["1231.03"])
    assert p is not None
    r = _row(p, "portfolio")
    assert r["priorBook"] == 1000.0
    assert r["currentProvision"] == 300.0
    assert r["currentReversal"] == 100.0
    assert r["currentBook"] == 1200.0
    assert p["_seeded_from"] == "tb_balance"
    assert p["_seeded_provision_codes"] == ["1231.03"]


def test_seed_row_field_names_match_frontend_model():
    """字段名逐字对齐前端 `K1BadDebtMainRow`（写错前端读不出）。"""
    src = (FRONTEND / "composables" / "useK1BadDebt.ts").read_text(encoding="utf-8")
    body = src.split("function createFixedMainRow", 1)[1].split("\n}", 1)[0]
    fe_keys = set(re.findall(r"^\s{4}([A-Za-z][A-Za-z0-9]*):", body, flags=re.M))
    assert fe_keys, "前端 createFixedMainRow 字段抽取为空（正则失效）"
    p = build_k1_bad_debt_seed_from_tb(
        [_leaf("1231.03", opening=1.0, closing=1.0)], ["1231.03"]
    )
    assert p is not None
    assert fe_keys <= set(_row(p, "portfolio").keys()), fe_keys - set(_row(p, "portfolio").keys())


def test_three_fixed_rows_present_and_individual_zero():
    """客户科目表无「单项 vs 组合」维度 → 单项行留零（宁缺勿造），总额进组合行。"""
    p = build_k1_bad_debt_seed_from_tb(
        [_leaf("1231.03", opening=10.0, credit=5.0, closing=15.0)], ["1231.03"]
    )
    assert [r["category"] for r in p["mainRows"]] == ["individual", "portfolio", "total"]
    ind = _row(p, "individual")
    assert ind["priorBook"] == 0.0 and ind["currentProvision"] == 0.0


def test_no_stage_movements_seeded():
    """三阶段拆分来自 K1-7，不 seed（避免把全额堆进第一阶段造成假披露）。"""
    p = build_k1_bad_debt_seed_from_tb(
        [_leaf("1231.03", opening=10.0, closing=10.0)], ["1231.03"]
    )
    assert "stageMovements" not in p


def test_absolute_normalisation_handles_negative_credit_convention():
    """`tb_balance` 两种符号约定并存 → 聚合结果取 abs 后同解。"""
    a = build_k1_bad_debt_seed_from_tb(
        [_leaf("1231.03", opening=-1000.0, credit=-300.0, debit=-100.0, closing=-1200.0)],
        ["1231.03"],
    )
    b = build_k1_bad_debt_seed_from_tb(
        [_leaf("1231.03", opening=1000.0, credit=300.0, debit=100.0, closing=1200.0)],
        ["1231.03"],
    )
    assert _row(a, "portfolio") == _row(b, "portfolio")


# ─────────────────── 宁缺勿造 / fail-open ───────────────────


@pytest.mark.parametrize(
    "leaves,prefixes",
    [
        ([], ["1231.03"]),
        ([_leaf("1231.03")], []),
        ([_leaf("1231.03")], ["1231.03"]),                 # 全零
        ([_leaf("1231.02", opening=999.0)], ["1231.03"]),  # 前缀不命中
    ],
)
def test_returns_none_when_nothing_to_seed(leaves, prefixes):
    assert build_k1_bad_debt_seed_from_tb(leaves, prefixes) is None


def test_provision_prefix_isolates_other_receivable_bad_debt():
    """🔴 只取 `1231.03`：`1231.02`（应收账款坏账）不得混入（K1 曾虚增 31.6 倍）。"""
    leaves = [
        _leaf("1231.02", opening=26_401_719.77, closing=26_401_719.77, name="坏账准备-应收账款"),
        _leaf("1231.03", opening=800_000.0, credit=100_217.36, closing=900_217.36),
    ]
    p = build_k1_bad_debt_seed_from_tb(leaves, ["1231.03"])
    assert _row(p, "portfolio")["currentBook"] == 900_217.36


# ─────────────────── Property 3：roll-forward 自洽 ───────────────────


@settings(max_examples=5, deadline=None)
@given(
    opening=st.floats(min_value=0, max_value=1e7, allow_nan=False, allow_infinity=False),
    credit=st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
    debit=st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
    closing=st.floats(min_value=0, max_value=1e7, allow_nan=False, allow_infinity=False),
)
def test_property_roll_forward_self_consistent(opening, credit, debit, closing):
    leaves = [_leaf("1231.03", opening=opening, credit=credit, debit=debit, closing=closing)]
    p = build_k1_bad_debt_seed_from_tb(leaves, ["1231.03"])
    if p is None:
        assert all(abs(v) < EPS for v in (opening, credit, debit, closing))
        return
    r = _row(p, "portfolio")
    derived = (
        r["priorAudited"] + r["currentProvision"] + r["currentOtherIncrease"]
        - r["currentReversal"] - r["currentWriteOff"] - r["currentOtherDecrease"]
    )
    assert abs(derived - r["currentBook"]) < 0.02
    assert abs(r["currentBook"] - round(closing * 100) / 100) < 0.05


def test_residual_goes_to_other_increase_or_decrease():
    """账套 closing 与滚存不等（如含其他减少）时，残差记入其他增减保持自洽。"""
    p = build_k1_bad_debt_seed_from_tb(
        [_leaf("1231.03", opening=1000.0, credit=0.0, debit=0.0, closing=900.0)], ["1231.03"]
    )
    r = _row(p, "portfolio")
    assert r["currentOtherDecrease"] == 100.0
    assert r["currentOtherIncrease"] == 0.0
    assert r["currentBook"] == 900.0

    p2 = build_k1_bad_debt_seed_from_tb(
        [_leaf("1231.03", opening=1000.0, credit=0.0, debit=0.0, closing=1100.0)], ["1231.03"]
    )
    r2 = _row(p2, "portfolio")
    assert r2["currentOtherIncrease"] == 100.0
    assert r2["currentBook"] == 1100.0


# ─────────────────── 手工优先 ───────────────────


def test_seed_writes_into_snapshot():
    snap: dict = {}
    p = build_k1_bad_debt_seed_from_tb(
        [_leaf("1231.03", opening=10.0, closing=10.0)], ["1231.03"]
    )
    assert seed_k1_bad_debt(snap, p) is True
    assert K1_BAD_DEBT_ITEM_ID in snap
    assert json.loads(snap[K1_BAD_DEBT_ITEM_ID]["remark"])["_seeded_from"] == "tb_balance"


def test_seed_skipped_when_manual_amount_present():
    manual = {"version": 2, "mainRows": [
        {"category": "portfolio", "isSubRow": False, "priorBook": 1.0},
    ]}
    snap = {K1_BAD_DEBT_ITEM_ID: {"conclusion": "", "remark": json.dumps(manual)}}
    p = build_k1_bad_debt_seed_from_tb(
        [_leaf("1231.03", opening=10.0, closing=10.0)], ["1231.03"]
    )
    assert seed_k1_bad_debt(snap, p) is False
    assert json.loads(snap[K1_BAD_DEBT_ITEM_ID]["remark"]) == manual


def test_seed_skipped_when_individual_sub_row_present():
    manual = {"version": 2, "mainRows": [
        {"category": "individual", "isSubRow": True, "label": "某公司"},
    ]}
    snap = {K1_BAD_DEBT_ITEM_ID: {"conclusion": "", "remark": json.dumps(manual)}}
    p = build_k1_bad_debt_seed_from_tb(
        [_leaf("1231.03", opening=10.0, closing=10.0)], ["1231.03"]
    )
    assert seed_k1_bad_debt(snap, p) is False


@pytest.mark.parametrize("raw", ["", None, "null", "{}", "not-json", '{"mainRows":[]}',
                                 '{"mainRows":[{"category":"portfolio","priorBook":0}]}'])
def test_seed_applies_when_existing_is_empty_shaped(raw):
    snap = {K1_BAD_DEBT_ITEM_ID: {"conclusion": "", "remark": raw}}
    p = build_k1_bad_debt_seed_from_tb(
        [_leaf("1231.03", opening=10.0, closing=10.0)], ["1231.03"]
    )
    assert seed_k1_bad_debt(snap, p) is True


def test_seed_noop_when_payload_none():
    snap: dict = {}
    assert seed_k1_bad_debt(snap, None) is False
    assert snap == {}


def test_guard_detects_regression_on_manual_priority():
    """反向自检：把手工判定改成恒 False 就会覆盖手工数据 → 断言必须能抓到。"""
    manual = {"version": 2, "mainRows": [
        {"category": "portfolio", "isSubRow": False, "priorBook": 12345.0},
    ]}
    snap = {K1_BAD_DEBT_ITEM_ID: {"conclusion": "", "remark": json.dumps(manual)}}
    before = snap[K1_BAD_DEBT_ITEM_ID]["remark"]
    seed_k1_bad_debt(
        snap,
        build_k1_bad_debt_seed_from_tb(
            [_leaf("1231.03", opening=1.0, closing=1.0)], ["1231.03"]
        ),
    )
    assert snap[K1_BAD_DEBT_ITEM_ID]["remark"] == before
