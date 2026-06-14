"""程序表适用性自动填充 PBT

Property: 对任意 business_category，A1 第15/16项仅 A/B 类适用（C 类为 na）。
max_examples=5
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.procedure_table_auto_service import get_template, ProcedureTableService

category_st = st.sampled_from(["A1", "A3", "B1", "B4", "C"])


@given(category=category_st)
@settings(max_examples=5, deadline=None)
def test_a1_item15_applicable_by_category(category):
    """Property: A1 第15项(质控复核)仅 A/B 适用"""
    template = get_template("A1")
    assert template is not None
    item15 = next(i for i in template["items"] if i["seq"] == 15)

    # 直接调用 _check_applicable 逻辑
    svc = ProcedureTableService.__new__(ProcedureTableService)
    result = svc._check_applicable(item15, category)

    prefix = category[0].upper()
    if prefix in ("A", "B"):
        assert result == "yes"
    else:
        assert result == "na"


@given(category=category_st)
@settings(max_examples=5, deadline=None)
def test_a1_item16_a_only(category):
    """Property: A1 第16项(专委会)仅 A 类适用"""
    template = get_template("A1")
    assert template is not None
    item16 = next(i for i in template["items"] if i["seq"] == 16)

    svc = ProcedureTableService.__new__(ProcedureTableService)
    result = svc._check_applicable(item16, category)

    prefix = category[0].upper()
    if prefix == "A":
        assert result == "yes"
    else:
        assert result == "na"


def test_all_templates_load():
    """所有 17 张表都能加载"""
    from app.services.procedure_table_auto_service import list_table_codes
    codes = list_table_codes()
    assert len(codes) == 17
    assert "A1" in codes
    assert "A17" in codes
