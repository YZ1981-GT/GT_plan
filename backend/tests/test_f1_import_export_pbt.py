"""F1 导入导出 Round-Trip 守卫（F1-5 长期挂款）

Validates: F1-5 export → import 字段等价（对齐 HTML 13 列）。
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings as hyp_settings
from hypothesis import strategies as st

from app.routers.wp_render_strategies._f1_import_export import (
    _F1_5_HEADERS,
    _export_f1_5_row,
    _parse_f1_5_row,
)

st_float = st.floats(min_value=-1e8, max_value=1e8, allow_nan=False, allow_infinity=False)
st_yn = st.sampled_from(["", "Y", "N"])

st_f1_5_row = st.fixed_dictionaries({
    "customerName": st.text(min_size=1, max_size=20, alphabet=st.characters(categories=("L", "N"))),
    "endBalance": st_float,
    "aging": st.sampled_from(["1-2年", "2-3年", "3年以上"]),
    "businessDescription": st.text(min_size=0, max_size=30, alphabet=st.characters(categories=("L",))),
    "reason": st.text(min_size=0, max_size=30, alphabet=st.characters(categories=("L",))),
    "plan": st.text(min_size=0, max_size=20, alphabet=st.characters(categories=("L",))),
    "isLitigation": st_yn,
    "transferToOtherReceivable": st_yn,
    "badDebtProvision": st_float,
    "postSettlementAmount": st_float,
    "supportingEvidence": st.text(min_size=0, max_size=20, alphabet=st.characters(categories=("L",))),
    "remark": st.text(min_size=0, max_size=20, alphabet=st.characters(categories=("L",))),
})


def _approx_eq(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(float(a) - float(b)) <= tol


@hyp_settings(max_examples=8)
@given(row=st_f1_5_row)
def test_f1_5_export_import_roundtrip(row: dict) -> None:
    """导出行 → 按表头解析 → 关键字段等价。"""
    exported = _export_f1_5_row(row)
    assert len(exported) == len(_F1_5_HEADERS)
    parsed = _parse_f1_5_row(tuple(exported), list(_F1_5_HEADERS))

    assert parsed["customerName"] == row["customerName"]
    assert _approx_eq(parsed["endBalance"], row["endBalance"])
    assert parsed["aging"] == row["aging"]
    assert parsed["businessDescription"] == row["businessDescription"]
    assert parsed["reason"] == row["reason"]
    assert parsed["plan"] == row["plan"]
    assert parsed["isLitigation"] == row["isLitigation"]
    assert parsed["transferToOtherReceivable"] == row["transferToOtherReceivable"]
    assert _approx_eq(parsed["badDebtProvision"], row["badDebtProvision"])
    assert _approx_eq(parsed["postSettlementAmount"], row["postSettlementAmount"])
    # 审定余额 = 期末 − 坏账（export 侧自动补）
    assert _approx_eq(parsed["auditedBalance"], row["endBalance"] - row["badDebtProvision"])


def test_f1_5_headers_aligned_with_html() -> None:
    assert "债务人名称" in _F1_5_HEADERS
    assert "计提坏账准备金额" in _F1_5_HEADERS
    assert "是否转入其他应收款" in _F1_5_HEADERS
    assert len(_F1_5_HEADERS) == 13
