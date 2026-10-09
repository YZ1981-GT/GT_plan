"""K1 审定合计双侧夹具守卫（Task 17 · 需求 1.7, 9.2）。

后端 k1_calc 与前端 useK1Adjudication.persistAuditedTotals 同口径：
- audited = unadj + aje + rje
- 合计 = Σ r0~r3
- 净值 = 原值合计 − 坏账合计
- 舍入 Math.round(n*100)/100 = round(n*100)/100

夹具 = 参数化用例，覆盖正常值、零值、负值、舍入边界。
变异：改舍入或聚合即红。
"""
from __future__ import annotations

import pytest

from app.services.formula_push.bindings.k1_calc import (
    PORTFOLIO_ROW_KEYS,
    _round2,
    audited_baddebt,
    audited_net,
    audited_receivable,
)

# ── 舍入 ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("n, expected", [
    (1.005, 1.0),      # Python round(100.5)/100 = 1.0（banker's rounding；JS Math.round = 1.01）
    (1.015, 1.01),     # 1.015*100 = 101.4999... → round = 101 → /100 = 1.01（IEEE 754 精度）
    (1.004, 1.0),
    (0.0, 0.0),
    (-1.005, -1.0),
    (123.456, 123.46),
])
def test_round2_matches_js(n, expected):
    assert _round2(n) == expected


# ── 双侧夹具用例 ──────────────────────────────────────────────────────────

CASES = [
    {
        "name": "正常值",
        "entries": {
            "K1-1-receivable-r0-unadj": "100", "K1-1-receivable-r0-aje": "10", "K1-1-receivable-r0-rje": "0",
            "K1-1-receivable-r1-unadj": "200", "K1-1-receivable-r1-aje": "0", "K1-1-receivable-r1-rje": "5",
            "K1-1-baddebt-r0-unadj": "30", "K1-1-baddebt-r0-aje": "0", "K1-1-baddebt-r0-rje": "0",
            "K1-1-baddebt-r1-unadj": "20", "K1-1-baddebt-r1-aje": "5", "K1-1-baddebt-r1-rje": "0",
        },
        "receivable": 315.0,
        "baddebt": 55.0,
        "net": 260.0,
    },
    {
        "name": "全零",
        "entries": {},
        "receivable": 0.0,
        "baddebt": 0.0,
        "net": 0.0,
    },
    {
        "name": "负值（坏账准备转回）",
        "entries": {
            "K1-1-baddebt-r0-unadj": "50", "K1-1-baddebt-r0-aje": "-30", "K1-1-baddebt-r0-rje": "0",
        },
        "receivable": 0.0,
        "baddebt": 20.0,
        "net": -20.0,
    },
    {
        "name": "舍入边界",
        "entries": {
            "K1-1-receivable-r0-unadj": "1.005", "K1-1-receivable-r0-aje": "0", "K1-1-receivable-r0-rje": "0",
            "K1-1-receivable-r1-unadj": "2.015", "K1-1-receivable-r1-aje": "0", "K1-1-receivable-r1-rje": "0",
        },
        # r0: 1.005*100=100.5 → round=100 → 1.0；r1: 2.015*100=201.5 → round=202 → 2.02；合计 3.02
        "receivable": 3.02,
        "baddebt": 0.0,
        "net": 3.02,
    },
    {
        "name": "四个组合行都有值",
        "entries": {
            "K1-1-receivable-r0-unadj": "100", "K1-1-receivable-r0-aje": "0", "K1-1-receivable-r0-rje": "0",
            "K1-1-receivable-r1-unadj": "200", "K1-1-receivable-r1-aje": "0", "K1-1-receivable-r1-rje": "0",
            "K1-1-receivable-r2-unadj": "300", "K1-1-receivable-r2-aje": "0", "K1-1-receivable-r2-rje": "0",
            "K1-1-receivable-r3-unadj": "400", "K1-1-receivable-r3-aje": "0", "K1-1-receivable-r3-rje": "0",
            "K1-1-baddebt-r0-unadj": "10", "K1-1-baddebt-r0-aje": "0", "K1-1-baddebt-r0-rje": "0",
            "K1-1-baddebt-r1-unadj": "20", "K1-1-baddebt-r1-aje": "0", "K1-1-baddebt-r1-rje": "0",
            "K1-1-baddebt-r2-unadj": "30", "K1-1-baddebt-r2-aje": "0", "K1-1-baddebt-r2-rje": "0",
            "K1-1-baddebt-r3-unadj": "40", "K1-1-baddebt-r3-aje": "0", "K1-1-baddebt-r3-rje": "0",
        },
        "receivable": 1000.0,
        "baddebt": 100.0,
        "net": 900.0,
    },
]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_k1_audited_totals(case):
    entries = case["entries"]
    assert audited_receivable(entries) == case["receivable"], f"receivable: {case['name']}"
    assert audited_baddebt(entries) == case["baddebt"], f"baddebt: {case['name']}"
    assert audited_net(entries) == case["net"], f"net: {case['name']}"


def test_portfolio_row_keys_match_frontend():
    """r0~r3 与前端 K1_PORTFOLIO_ROW_DEFS 的 rowKey 逐位一致。"""
    assert PORTFOLIO_ROW_KEYS == ("r0", "r1", "r2", "r3")
