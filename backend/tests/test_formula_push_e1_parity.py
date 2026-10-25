"""E1 公式推送 · 前后端同式双侧夹具（后端侧）。

spec: chain-closure-phase2-formula-push-engine · design §一.3 / 任务 9

夹具 ``tests/fixtures/formula_push_e1_parity.json`` 由前端 vitest
``e1FormulaPushParity.spec.ts`` 用**真 composable / 纯函数**按引擎同一管线产出
（种子 → 明细合计 → 审定合计 / 语义槽 → 披露主表）。本测试用后端
``formula_push.bindings.e1_calc`` 走同一管线，要求**逐值相等**（字符串逐字、浮点逐位）：
任一侧改算式另一侧必红。

另有夹具自检（防空转）：用例数、各级输出非空、至少一个大厅调整与扣减映射真实生效。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.formula_push.bindings import e1_calc
from app.services.formula_push.js_compat import js_number_to_string

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "formula_push_e1_parity.json"
DOC = json.loads(FIXTURE.read_text(encoding="utf-8"))
CASES = DOC["cases"]


def _s(value: float | None) -> str | None:
    return None if value is None else js_number_to_string(value)


def _pipeline(case: dict) -> dict:
    """与 vitest `computeCase` 同一管线，只用后端实现。"""
    entries: dict = dict(case["entries"])
    prefill = case["fourTablePrefill"]
    account_prefill = case["accountPrefill"]
    variant, _defaulted = e1_calc.bank_variant(entries)

    cash_seeds = [
        {k: r[k] for k in ("id", "opening", "increase", "decrease", "fxRate")}
        for r in (e1_calc.build_cash_seed_rows(prefill.get("cash")) or [])
    ]
    bank_seeds = [
        {k: r[k] for k in ("id", "opening", "increase", "decrease")}
        for r in (e1_calc.bank_seed_rows(prefill, account_prefill) or [])
    ]

    detail: dict[str, str | None] = {}
    for period in e1_calc.PERIODS:
        detail[e1_calc.CASH_TOTAL_KEYS[period]] = _s(
            e1_calc.cash_detail_total(entries, prefill.get("cash") or [], period)
        )
    for group in e1_calc.BANK_GROUPS:
        for period in e1_calc.PERIODS:
            value = e1_calc.bank_detail_total(entries, variant, prefill, group, period)
            detail[e1_calc.bank_total_key(group, period)] = (
                None if isinstance(value, e1_calc.Unavailable) else _s(value)
            )
    # 与 vitest 的 cash/bank 键序一致（cash 两键在前）
    detail = {k: detail[k] for k in case["expected"]["detail"]}

    stage2 = dict(entries)
    stage2.update({k: v for k, v in detail.items() if v is not None})
    adj_totals: dict[str, str | None] = {}
    for code in ("1001", "1002", "1012"):
        for period in ("ending", "opening"):
            adj_totals[e1_calc.adj_total_key(code, period)] = _s(e1_calc.adjudicated_total(stage2, code, period))
    slots: dict[str, str | None] = {}
    for slot in ("finance_co", "accrued", "digital"):
        for period in ("ending", "opening"):
            slots[e1_calc.main_row_slot_key(slot, period)] = _s(e1_calc.main_row_slot(stage2, slot, period))

    stage3 = dict(stage2)
    stage3.update({k: v for k, v in adj_totals.items() if v is not None})
    stage3.update({k: v for k, v in slots.items() if v is not None})
    disclosure = {
        v: [
            {
                "key": r["key"],
                "endingAmount": r["ending"],
                "openingAmount": r["opening"],
                "endingResolved": r["ending_resolved"],
                "openingResolved": r["opening_resolved"],
            }
            for r in e1_calc.disclosure_main_rows(stage3, v)
        ]
        for v in ("listed", "soe")
    }
    return {
        "variant": variant,
        "cashSeeds": cash_seeds,
        "bankSeeds": bank_seeds,
        "detail": detail,
        "adjTotals": adj_totals,
        "slots": slots,
        "disclosure": disclosure,
    }


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_backend_matches_frontend_fixture(case):
    got = _pipeline(case)
    want = case["expected"]
    for section in ("variant", "cashSeeds", "bankSeeds", "detail", "adjTotals", "slots", "disclosure"):
        assert got[section] == want[section], f"{case['name']}.{section} 前后端不一致"


def test_constants_match_frontend():
    c = DOC["constants"]
    assert list(e1_calc.HALL_ADJ_ITEM_KEYS) == c["hallAdjItemKeys"]
    assert dict(e1_calc.MAIN_ROW_SLOTS) == c["mainRowSlots"]
    assert {k: list(v) for k, v in e1_calc.MAIN_ROW_DEDUCTIONS.items()} == c["mainRowDeductions"]
    for variant in ("listed", "soe"):
        backend = [
            {
                "key": r["key"], "label": r["label"], "noteLabel": r.get("note_label"),
                "crossKey": r["cross_key"], "isTotal": bool(r.get("is_total")), "isMemo": bool(r.get("is_memo")),
            }
            for r in e1_calc.MAIN_ROWS[variant]
        ]
        assert backend == c["mainRows"][variant], f"{variant} 披露行集前后端不一致"


def test_fixture_is_not_vacuous():
    assert [c["name"] for c in CASES] == [
        "listed_rmb_rows", "soe_multi_accounts", "no_rows_leaf_fallback", "untouched_default_cash",
    ]
    first = CASES[0]["expected"]
    # 大厅调整生效：1001 期末 = 现金明细期末 + E1-5(-10.5) + 大厅(100)
    cash = float(first["detail"]["E1-cash-detail-total-unaudited"])
    assert float(first["adjTotals"]["E1-adj-total-1001"]) == pytest.approx(cash - 10.5 + 100)
    # 扣减映射生效：银行存款行 = 1002 审定 − 存放财务公司款项槽
    bank_row = next(r for r in first["disclosure"]["listed"] if r["key"] == "bank")
    assert bank_row["endingAmount"] == pytest.approx(
        float(first["adjTotals"]["E1-adj-total-1002"]) - float(first["slots"]["E1-adj-slot-finance_co"])
    )
    # 账户级优先：soe 用例的种子全是 -acct- 且重复账号补序号
    ids = [r["id"] for r in CASES[1]["expected"]["bankSeeds"]]
    assert all("-acct-" in i for i in ids) and "bank-principal-institution-acct-6222-1-2" in ids
    # 无明细行兜底：财务公司分组无从计算（None），其余取四表叶子合计
    fallback = CASES[2]["expected"]["detail"]
    assert fallback["E1-bank-detail-finance-total-unaudited"] is None
    assert fallback["E1-bank-detail-principal-total-unaudited"] == "120.3"
