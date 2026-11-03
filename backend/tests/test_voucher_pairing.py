"""多借多贷精确配对（spec voucher-identity-writeback-and-audit-phase 需求 3、任务 7，design §3）。

纯函数用例：真实账向量（四川物流 FY-0012、一对多、红蓝混合、借贷双填、超 200 行）+ 合成凭证
（等额多解、组内唯一性、第 6 步校验、对侧单科目、预算耗尽）+ 性质测试（金额守恒、不出现
凭证外金额、与输入顺序无关）。接入（抽凭补全、凭证穿透、下钻）见 test_voucher_pairing_wiring.py。
"""

from __future__ import annotations

import json
import random
import time
from decimal import Decimal
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.services.voucher_identity import annotate_lines
from app.services.voucher_pairing import (
    LINE_LIMIT,
    MULTI_ACCOUNT_LABEL,
    annotate_pairing,
    counterpart_label,
    pair_voucher,
)

REAL = json.loads((Path(__file__).parent / "fixtures" / "voucher_real_ledger_vectors.json")
                  .read_text(encoding="utf-8"))["vouchers"]


def _real(name: str) -> list[dict]:
    return annotate_lines([dict(r) for r in REAL[name]])


def _line(acct: str, side: str, amount: str, i: int) -> dict:
    return {
        "year": "2025", "company_code": "001", "voucher_date": "2025-03-31", "voucher_type": "记",
        "voucher_no": "0099", "account_code": acct, "account_name": f"科目{acct}",
        "debit_amount": amount if side == "D" else None, "credit_amount": amount if side == "C" else None,
        "summary": "", "id": f"L{i:04d}",
    }


def _voucher(*specs: tuple[str, str, str]) -> list[dict]:
    return annotate_lines([_line(a, s, amt, i) for i, (a, s, amt) in enumerate(specs)])


def _view(rows: list[dict], result: dict) -> dict:
    """(借贷栏, 科目, 金额) → (状态, 依据, [(对方科目, 金额, 是否指认到行)])，用于断言。"""
    out = {}
    for r in rows:
        p = result[r["line_fp"]]
        amount = r["debit_amount"] if r["side"] == "D" else r["credit_amount"]
        key = (r["side"], r["account_code"], amount)
        assert key not in out, f"断言视图要求 (借贷栏, 科目, 金额) 唯一：{key}"
        out[key] = (p["status"], p["basis"],
                    sorted((c["account_code"], c["amount"], c["line_fp"] is not None) for c in p["counterparts"]))
    return out


# ─── 真实账向量 ────────────────────────────────────────────────────────────────


def test_fy0012_bank_payments_pair_to_payroll_and_expense_to_credit_payroll():
    """需求 3.8：两笔银行付款（2,000 + 1,680）配到应付职工薪酬 3,680；管理费用 3,680 配到贷方应付职工薪酬。"""
    rows = _real("fy0012_many_to_many")
    view = _view(rows, pair_voucher(rows))
    payroll = "2211.01.99.04"
    assert view[("D", payroll, "3680.00")] == (
        "paired", "one_to_many", [("1002", "1680.00", True), ("1002", "2000.00", True)])
    assert view[("C", "1002", "2000.00")] == ("paired", "many_to_one", [(payroll, "2000.00", True)])
    assert view[("C", "1002", "1680.00")] == ("paired", "many_to_one", [(payroll, "1680.00", True)])
    # 同科目借贷对冲（借 2211 / 贷 2211）不是唯一解：贷方 2211 优先配不同科目的管理费用
    assert view[("D", "6602.01.99", "3680.00")] == ("paired", "one_to_one", [(payroll, "3680.00", True)])
    assert view[("C", payroll, "3680.00")] == ("paired", "one_to_one", [("6602.01.99", "3680.00", True)])


def test_single_side_lists_each_counterpart_with_its_own_amount():
    """需求 3.1：本侧只有一条，对侧每条按各自金额列出。"""
    rows = _real("one_to_many")
    view = _view(rows, pair_voucher(rows))
    assert view[("D", "1221.98.08", "31327.12")] == (
        "paired", "single_side", [("2221.01.01", "1773.23", True), ("6001.14.01", "29553.89", True)])
    assert view[("C", "2221.01.01", "1773.23")] == ("paired", "single_side", [("1221.98.08", "1773.23", True)])
    assert view[("C", "6001.14.01", "29553.89")] == ("paired", "single_side", [("1221.98.08", "29553.89", True)])


def test_red_lines_pair_only_with_red_and_blue_with_blue():
    """需求 3.5：多对多时红字只与红字凑（红字借方 -11,610 = 两笔红字贷方），蓝字贷方 100.84 = 四笔蓝字借方。"""
    rows = _real("red_blue_mixed")
    result = pair_voucher(rows)
    assert {p["status"] for p in result.values()} == {"paired"}
    by_fp = {r["line_fp"]: r for r in rows}
    for fp, p in result.items():
        own = by_fp[fp]
        own_red = Decimal(own["debit_amount"] or own["credit_amount"]) < 0
        for c in p["counterparts"]:
            other = by_fp[c["line_fp"]]
            assert (Decimal(other["debit_amount"] or other["credit_amount"]) < 0) == own_red
    view = _view(rows, result)
    assert view[("D", "1122.02", "-11610.00")] == (
        "paired", "one_to_many", [("2221.01.01", "-1335.66", True), ("6001.11.01", "-10274.34", True)])
    assert view[("C", "1002", "100.84")][1] == "one_to_many"
    assert len(view[("C", "1002", "100.84")][2]) == 4


def test_both_sides_filled_is_unknown_side():
    rows = _real("both_sides_filled")
    assert {p["status"] for p in pair_voucher(rows).values()} == {"unknown_side"}
    assert all(counterpart_label(p) is None for p in pair_voucher(rows).values())


def test_voucher_over_limit_is_not_paired_line_by_line():
    """需求 3.6：超过 200 行不做配对；对侧只有一个科目时科目是确定的，给科目级结果，其余标 large + 汇总。"""
    rows = _real("large_over_200")
    assert len(rows) > LINE_LIMIT
    result = pair_voucher(rows)
    statuses = {p["status"] for p in result.values()}
    assert "large" in statuses and statuses <= {"large", "paired"}
    for p in result.values():
        assert all(c["line_fp"] is None for c in p["counterparts"]), "超限凭证不许指认到对侧某一行"
        if p["status"] == "paired":
            assert p["basis"] == "single_account" and len(p["counterparts"]) == 1
        else:
            assert len(p["counterpart_summary"]) >= 2 and counterpart_label(p) == (MULTI_ACCOUNT_LABEL,) * 2


# ─── 合成凭证 ──────────────────────────────────────────────────────────────────


def test_equal_amounts_with_two_solutions_are_multi():
    rows = _voucher(("6602", "D", "100.00"), ("6603", "D", "100.00"), ("1002", "C", "100.00"),
                    ("2211", "C", "100.00"))
    result = pair_voucher(rows)
    assert {p["status"] for p in result.values()} == {"multi"}
    for p in result.values():
        assert len(p["counterpart_summary"]) == 2 and p["counterparts"] == []
        assert counterpart_label(p) == (MULTI_ACCOUNT_LABEL, MULTI_ACCOUNT_LABEL)


def test_subset_solution_must_be_unique_for_every_member():
    """贷方 100 只出现在 {100,200}→300 一个组里，但借方 300 还有 {150,150} 这个解 ⇒ 不唯一，全部 multi。"""
    rows = _voucher(("6602", "D", "300.00"), ("6603", "D", "120.00"), ("6604", "D", "180.00"),
                    ("1002", "C", "100.00"), ("2211", "C", "200.00"), ("2241", "C", "150.00"),
                    ("2202", "C", "150.00"))
    assert {p["status"] for p in pair_voucher(rows).values()} == {"multi"}


def test_many_to_one_after_one_to_one():
    rows = _voucher(("6602", "D", "30.00"), ("6603", "D", "70.00"), ("6604", "D", "50.00"),
                    ("1002", "C", "100.00"), ("2211", "C", "50.00"))
    view = _view(rows, pair_voucher(rows))
    assert view[("D", "6604", "50.00")] == ("paired", "one_to_one", [("2211", "50.00", True)])
    assert view[("C", "1002", "100.00")] == ("paired", "one_to_many", [("6602", "30.00", True), ("6603", "70.00", True)])
    assert view[("D", "6602", "30.00")] == ("paired", "many_to_one", [("1002", "30.00", True)])


def test_same_account_offset_is_not_assumed_when_not_unique():
    rows = _voucher(("2211", "D", "3680.00"), ("6602", "D", "3680.00"), ("2211", "C", "3680.00"),
                    ("1002", "C", "3680.00"))
    assert {p["status"] for p in pair_voucher(rows).values()} == {"multi"}


def test_unbalanced_single_side_fails_validation_and_is_not_paired():
    """第 6 步：借方一行 100.00、贷方合计 99.99 ⇒ 借方的对方金额对不上本行金额，降为 multi；
    贷方两行的对侧只有一个科目，照给科目级结果（对方科目确定，金额 = 本行金额）。"""
    rows = _voucher(("1221", "D", "100.00"), ("2221", "C", "10.00"), ("6001", "C", "89.99"))
    view = _view(rows, pair_voucher(rows))
    assert view[("D", "1221", "100.00")] == ("multi", None, [])
    assert view[("C", "2221", "10.00")] == ("paired", "single_account", [("1221", "10.00", False)])
    assert view[("C", "6001", "89.99")] == ("paired", "single_account", [("1221", "89.99", False)])


def test_single_opposite_account_gives_account_level_counterpart():
    """需求 3.1 后半：对侧只有一个科目 ⇒ 对方科目 + 本行金额（两行贷方 70 / 80 配不到具体哪一行）。"""
    rows = _voucher(("6602.01", "D", "100.00"), ("6602.02", "D", "50.00"), ("1002", "C", "70.00"),
                    ("1002", "C", "80.00"))
    view = _view(rows, pair_voucher(rows))
    assert view[("D", "6602.01", "100.00")] == ("paired", "single_account", [("1002", "100.00", False)])
    assert view[("D", "6602.02", "50.00")] == ("paired", "single_account", [("1002", "50.00", False)])
    assert view[("C", "1002", "70.00")] == ("multi", None, [])
    assert counterpart_label(pair_voucher(rows)[rows[0]["line_fp"]]) == ("1002", "科目1002")


def test_combination_budget_stops_search_without_partial_answers():
    """几十行小额分录凑一大额：组合数超过上限即停止搜索，余下 multi，不报错、不慢。"""
    rng = random.Random(7)
    small = [f"{rng.randint(100, 9999) / 100:.2f}" for _ in range(60)]
    total = sum(Decimal(x) for x in small)
    big_a = (total / 2).quantize(Decimal("0.01"))
    rows = _voucher(("6602", "D", str(big_a)), ("6603", "D", str(total - big_a)),
                    *[(f"2{i:03d}", "C", amt) for i, amt in enumerate(small)])
    t0 = time.perf_counter()
    result = pair_voucher(rows)
    assert time.perf_counter() - t0 < 5
    assert {p["status"] for p in result.values()} == {"multi"}


def test_counterpart_label_for_one_to_many_to_same_account():
    rows = _real("fy0012_many_to_many")
    result = pair_voucher(rows)
    by_key = {(r["side"], r["account_code"]): result[r["line_fp"]] for r in rows if r["account_code"] != "1002"}
    assert counterpart_label(by_key[("D", "2211.01.99.04")]) == ("1002", "银行存款")
    assert counterpart_label(by_key[("D", "6602.01.99")])[0] == "2211.01.99.04"
    one = _real("one_to_many")
    assert counterpart_label(pair_voucher(one)[one[0]["line_fp"]]) == (MULTI_ACCOUNT_LABEL,) * 2


def test_penetration_rows_of_large_voucher_omit_repeated_summary():
    """穿透响应本就是整张凭证：超限凭证每行同一份对侧汇总不逐行重复（抽凭样本照带，见上一条用例）。"""
    rows = annotate_pairing(_real("large_over_200"))
    large = [r["pairing"] for r in rows if r["pairing"]["status"] == "large"]
    assert large and all(p["counterpart_summary"] == [] and p["summary_omitted"] for p in large)
    direct = pair_voucher(_real("large_over_200"))
    assert all(direct[r["line_fp"]]["counterpart_summary"] for r in rows if r["pairing"]["status"] == "large")


def test_annotate_pairing_and_missing_fingerprints():
    rows = annotate_pairing(_real("fy0012_many_to_many"))
    assert all(r["pairing"]["status"] == "paired" for r in rows)
    bare = [{k: v for k, v in r.items() if k not in ("line_fp", "side", "voucher_key", "pairing")}
            for r in _real("fy0012_many_to_many")]
    assert pair_voucher(bare) == pair_voucher(_real("fy0012_many_to_many")), "没给指纹时按同一口径现算"


# ─── 性质测试 ──────────────────────────────────────────────────────────────────


_ACCOUNTS = ["1002", "1122", "2202", "2211", "6602"]


@st.composite
def _balanced_voucher(draw):
    debit = draw(st.lists(st.integers(-500, 3000).filter(bool), min_size=1, max_size=5))
    credit = draw(st.lists(st.integers(-500, 3000).filter(bool), min_size=1, max_size=5))
    gap = sum(debit) - sum(credit)
    if gap > 0:
        credit.append(gap)
    elif gap < 0:
        debit.append(-gap)
    specs = [(draw(st.sampled_from(_ACCOUNTS)), "D", f"{c / 100:.2f}") for c in debit]
    specs += [(draw(st.sampled_from(_ACCOUNTS)), "C", f"{c / 100:.2f}") for c in credit]
    return specs


@settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(specs=_balanced_voucher(), seed=st.integers(0, 10_000))
def test_paired_amounts_are_conserved_and_order_independent(specs, seed):
    rows = _voucher(*specs)
    result = pair_voucher(rows)
    amounts = {Decimal(r["debit_amount"] or r["credit_amount"]) for r in rows}
    by_fp = {r["line_fp"]: r for r in rows}
    for fp, p in result.items():
        if p["status"] != "paired":
            continue
        own = Decimal(by_fp[fp]["debit_amount"] or by_fp[fp]["credit_amount"])
        assert sum(Decimal(c["amount"]) for c in p["counterparts"]) == own
        assert all(Decimal(c["amount"]) in amounts for c in p["counterparts"]), "不出现凭证外金额"
    shuffled = rows[:]
    random.Random(seed).shuffle(shuffled)
    assert pair_voucher(shuffled) == result
