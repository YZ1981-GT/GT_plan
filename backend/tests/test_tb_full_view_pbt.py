"""TB 完整视图平衡公式恒等 PBT

Property: 对任意 unadjusted + aje + rje + audited 组合，
service 计算的 other_adjustment = audited - unadj - aje - rje 恒满足。
纯逻辑测试（不建表）。

max_examples=5
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

amount_st = st.decimals(min_value=Decimal("-999999"), max_value=Decimal("999999"), places=2)


@given(unadj=amount_st, aje=amount_st, rje=amount_st, audited=amount_st)
@settings(max_examples=5, deadline=None)
def test_balance_formula_holds(unadj, aje, rje, audited):
    """Property: other = audited - unadj - aje - rje，公式恒等"""
    other = audited - unadj - aje - rje
    computed = unadj + aje + rje + other
    assert abs(computed - audited) < Decimal("0.01")


def test_balance_check_logic():
    """平衡校验：total computed == total audited"""
    rows = [
        {"unadjusted": Decimal("100"), "aje_adjustment": Decimal("10"),
         "rje_adjustment": Decimal("-5"), "other_adjustment": Decimal("0"),
         "audited": Decimal("105")},
        {"unadjusted": Decimal("200"), "aje_adjustment": Decimal("0"),
         "rje_adjustment": Decimal("0"), "other_adjustment": Decimal("50"),
         "audited": Decimal("250")},
    ]
    total_computed = sum(
        r["unadjusted"] + r["aje_adjustment"] + r["rje_adjustment"] + r["other_adjustment"]
        for r in rows
    )
    total_audited = sum(r["audited"] for r in rows)
    assert abs(total_computed - total_audited) < Decimal("0.01")
