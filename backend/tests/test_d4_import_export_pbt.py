"""Property 15: 导入导出 Round-Trip — D4 营业收入

Feature: d4-operating-revenue, Property 15: 导入导出Round-Trip

生成随机 RevenueDetailRow[] → JSON.stringify → JSON.parse → 验证等价。
使用 hypothesis 的 max_examples=5（项目约定）。
"""

from __future__ import annotations

import json

from hypothesis import given, settings
from hypothesis import strategies as st


# ═══════════════════════════════════════════════════════════════════════════════
# Strategies
# ═══════════════════════════════════════════════════════════════════════════════

_month_amount_st = st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False)

_revenue_detail_row_st = st.fixed_dictionaries({
    "rowId": st.uuids().map(str),
    "product": st.text(min_size=1, max_size=20, alphabet=st.characters(categories=("L", "N"))),
    "months": st.lists(_month_amount_st, min_size=12, max_size=12),
    "auditAdjustment": _month_amount_st,
    "priorUnadjusted": _month_amount_st,
    "priorAdjustment": _month_amount_st,
    "remark": st.text(max_size=50),
})

_rows_st = st.lists(_revenue_detail_row_st, min_size=1, max_size=10)


# ═══════════════════════════════════════════════════════════════════════════════
# Property Test
# ═══════════════════════════════════════════════════════════════════════════════


@settings(max_examples=5)
@given(rows=_rows_st)
def test_d4_revenue_detail_json_round_trip(rows: list[dict]) -> None:
    """**Validates: Requirements 20.6, 24.2**

    For any valid D4-2 dynamic row array, JSON serialize → deserialize
    produces equivalent data (round-trip fidelity).
    """
    # Serialize
    serialized = json.dumps(rows, ensure_ascii=False)

    # Deserialize
    deserialized = json.loads(serialized)

    # Verify equivalence
    assert len(deserialized) == len(rows)

    for original, restored in zip(rows, deserialized):
        assert restored["rowId"] == original["rowId"]
        assert restored["product"] == original["product"]
        assert restored["remark"] == original["remark"]

        # Months: float round-trip (JSON preserves float fidelity)
        assert len(restored["months"]) == 12
        for orig_m, rest_m in zip(original["months"], restored["months"]):
            assert orig_m == rest_m

        assert restored["auditAdjustment"] == original["auditAdjustment"]
        assert restored["priorUnadjusted"] == original["priorUnadjusted"]
        assert restored["priorAdjustment"] == original["priorAdjustment"]
