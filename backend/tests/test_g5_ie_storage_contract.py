"""G5 IE 存储契约：nest/flat、利率、双写规格。"""

from __future__ import annotations


def test_g5_specs_use_conclusion_and_dual_write():
    from app.routers.wp_render_strategies._g5_long_term_receivable_import_export import _G5_SPECS

    assert set(_G5_SPECS) == {
        "G5-1", "G5-2", "G5-3", "G5-4", "G5-5", "G5-6", "G5-7", "G5-11", "G5-12",
    }
    for code, sp in _G5_SPECS.items():
        assert sp.get("storage_field") == "conclusion", code
        assert sp.get("dual_write") is True, code


def test_g5_5_nest_flatten_rate_roundtrip():
    from app.routers.wp_render_strategies._g5_long_term_receivable_import_export import (
        _flatten_lease_like_groups,
        _nest_lease_like_rows,
    )

    nested = {
        "groups": [{
            "id": "g1",
            "projectName": "租赁A",
            "basic": {"lessee": "甲", "implicitRate": 0.0525},
            "periods": [
                {"periodNo": 1, "openingReceivable": 100, "periodCollection": 10},
                {"periodNo": 2, "openingReceivable": 90, "periodCollection": 10},
            ],
        }],
        "conclusion": "",
    }
    flat = _flatten_lease_like_groups(nested, rate_key="implicitRate")
    assert len(flat) == 2
    assert flat[0]["implicitRate"] == 5.25
    restored = _nest_lease_like_rows(flat, rate_key="implicitRate")
    assert len(restored["groups"]) == 1
    assert restored["groups"][0]["basic"]["implicitRate"] == 0.0525
    assert len(restored["groups"][0]["periods"]) == 2


def test_g5_11_nest_flatten():
    from app.routers.wp_render_strategies._g5_long_term_receivable_import_export import (
        _flatten_g5_11,
        _nest_g5_11_rows,
    )

    nested = {
        "reversal": [{"seq": 1, "debtor": "A", "reversalAmount": 10, "accumulatedProvision": 20}],
        "writeoff": [{"seq": 1, "debtor": "B", "writeoffAmount": 5, "isRelatedParty": True}],
    }
    flat = _flatten_g5_11(nested)
    assert {r["section"] for r in flat} == {"reversal", "writeoff"}
    restored = _nest_g5_11_rows(flat)
    assert restored["reversal"][0]["debtor"] == "A"
    assert restored["writeoff"][0]["debtor"] == "B"


def test_g5_3_movement_schema():
    from app.routers.wp_render_strategies._g5_long_term_receivable_import_export import (
        _G5_3_HEADERS,
        _G5_3_KEYS,
        _G5_SPECS,
    )

    assert "openingUnadjusted" in _G5_3_KEYS
    assert "provisionIncrease" in _G5_3_KEYS
    assert "debtorOrGroup" not in _G5_3_KEYS
    assert "creditLossRate" not in _G5_3_KEYS
    assert len(_G5_3_HEADERS) == len(_G5_3_KEYS)
    assert _G5_SPECS["G5-3"]["field_keys"] == _G5_3_KEYS
