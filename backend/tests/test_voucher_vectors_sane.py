"""真实凭证夹具自检（spec voucher-identity-writeback-and-audit-phase 任务 1）。

夹具 ``fixtures/voucher_real_ledger_vectors.json`` 从真库只读导出，摘要与行 id 已匿名化（排序关系
不变）。后续配对、指纹、回填测试都读它；这里先确认夹具本身可信：每张凭证非空、属于同一张凭证、
借贷合计相等，且各自具备被选中的特征（多借多贷 / 同日同号不同凭证字 / 红蓝混合 / 双填 / 超 200 行）。
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.voucher_identity import SIDE_UNKNOWN, VoucherKey, side_of, to_decimal

FIXTURE = Path(__file__).parent / "fixtures" / "voucher_real_ledger_vectors.json"
DATA = json.loads(FIXTURE.read_text(encoding="utf-8"))
VOUCHERS: dict[str, list[dict]] = DATA["vouchers"]

#: 借贷双填凭证：每行借贷两栏同额，「借贷合计相等」对它没有意义，单独断言其特征。
DOUBLE_FILLED = {"both_sides_filled"}

EXPECTED = {
    "fy0012_many_to_many",
    "fy0003_same_day_same_no",
    "zz0003_same_day_same_no",
    "one_to_many",
    "red_blue_mixed",
    "both_sides_filled",
    "large_over_200",
}


def _sums(lines: list[dict]) -> tuple[Decimal, Decimal]:
    return (
        sum((to_decimal(x["debit_amount"]) for x in lines), Decimal("0")),
        sum((to_decimal(x["credit_amount"]) for x in lines), Decimal("0")),
    )


def _sides(lines: list[dict]) -> list[str]:
    return [side_of(x["debit_amount"], x["credit_amount"]) for x in lines]


def test_fixture_has_all_cases():
    assert set(VOUCHERS) == EXPECTED
    assert all(VOUCHERS[k] for k in EXPECTED)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_each_case_is_one_voucher(name):
    lines = VOUCHERS[name]
    keys = {VoucherKey.from_row(x) for x in lines}
    assert len(keys) == 1, f"{name} 混入了别的凭证：{keys}"
    ids = [x["id"] for x in lines]
    assert len(set(ids)) == len(ids)


@pytest.mark.parametrize("name", sorted(EXPECTED - DOUBLE_FILLED))
def test_debit_equals_credit(name):
    debit, credit = _sums(VOUCHERS[name])
    assert debit == credit, f"{name} 借 {debit} ≠ 贷 {credit}"


def test_double_filled_lines_are_unknown_side():
    lines = VOUCHERS["both_sides_filled"]
    assert all(s == SIDE_UNKNOWN for s in _sides(lines))
    assert all(to_decimal(x["debit_amount"]) == to_decimal(x["credit_amount"]) != 0 for x in lines)


def test_case_features():
    sides = _sides(VOUCHERS["fy0012_many_to_many"])
    assert sides.count("D") >= 2 and sides.count("C") >= 2

    sides = _sides(VOUCHERS["one_to_many"])
    assert sorted([sides.count("D"), sides.count("C")]) == [1, 2]

    fy = VoucherKey.from_row(VOUCHERS["fy0003_same_day_same_no"][0])
    zz = VoucherKey.from_row(VOUCHERS["zz0003_same_day_same_no"][0])
    assert (fy.company_code, fy.voucher_date, fy.voucher_no) == (zz.company_code, zz.voucher_date, zz.voucher_no)
    assert fy.voucher_type != zz.voucher_type

    amounts = [to_decimal(x["debit_amount"]) + to_decimal(x["credit_amount"]) for x in VOUCHERS["red_blue_mixed"]]
    assert any(a < 0 for a in amounts) and any(a > 0 for a in amounts)
    # 红字借方仍在借方栏
    assert any(s == "D" and to_decimal(x["debit_amount"]) < 0
               for s, x in zip(_sides(VOUCHERS["red_blue_mixed"]), VOUCHERS["red_blue_mixed"]))

    assert len(VOUCHERS["large_over_200"]) > 200


def test_counts_snapshot_shape():
    snap = DATA["counts_snapshot"]
    assert len(snap) == 7
    for name, c in snap.items():
        assert c["n_key"] >= c["n_no"] > 0, name
        if "n_date_no" in c:
            assert c["n_key"] >= c["n_date_no"] >= c["n_no"], name
    # 混凭证字的三套账：按 (日期, 号) 会把不同凭证并成一张
    for name in ("四川物流", "辽宁卫生", "宜宾临港"):
        assert snap[name]["n_key"] > snap[name]["n_date_no"], name
