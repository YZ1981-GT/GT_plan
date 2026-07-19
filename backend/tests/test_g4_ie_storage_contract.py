"""G4 SPPI/ECL/Main IE 存储契约：conclusion 优先 + remark 双写辅助。"""

from __future__ import annotations


def test_sppi_helpers_exported():
    from app.routers.wp_render_strategies._g4_bond_investment_sppi_import_export import (
        _load_canonical_rows,
        _upsert_dual_rows,
        _ITEM_IDS,
        _G4_6_SECTION_ITEM_IDS,
    )

    assert _ITEM_IDS["G4-5"] == "G4-5-questionnaire"
    assert "债券投资SPPI" in _G4_6_SECTION_ITEM_IDS
    assert callable(_load_canonical_rows)
    assert callable(_upsert_dual_rows)


def test_ecl_helpers_exported():
    from app.routers.wp_render_strategies._g4_bond_investment_ecl_import_export import (
        _load_canonical_rows,
        _load_canonical_payload,
        _upsert_dual_rows,
        _upsert_dual_payload,
        _load_g4_12_export_rows,
        _ITEM_IDS,
        _G4_12_ITEM_IDS,
    )

    assert _ITEM_IDS["G4-12"] == "G4-12-rows"
    assert _G4_12_ITEM_IDS["reversals"] == "G4-12-reversals"
    assert callable(_load_canonical_rows)
    assert callable(_load_canonical_payload)
    assert callable(_upsert_dual_rows)
    assert callable(_upsert_dual_payload)
    assert callable(_load_g4_12_export_rows)


def test_main_g4_4_rate_helpers():
    from app.routers.wp_render_strategies._g4_bond_investment_main_import_export import (
        _rate_to_percent,
        _rate_to_decimal,
        _flatten_g4_4_groups,
        _nest_g4_4_flat_rows,
        _G4_4_PRIMARY_ITEM_ID,
    )

    assert _G4_4_PRIMARY_ITEM_ID == "G4-4-interest-calc"
    assert _rate_to_percent(0.0525) == 5.25
    assert _rate_to_decimal(5.25) == 0.0525
    # 已是百分数时不再 *100
    assert _rate_to_percent(5.25) == 5.25
    # 已是小数时不再 /100
    assert _rate_to_decimal(0.05) == 0.05

    nested = [{
        "id": "g1",
        "projectName": "债A",
        "initial": {"couponRate": 0.03, "effectiveRate": 0.035, "faceValueTotal": 100},
        "periods": [{"cutoffDate": "2025-12-31", "effectiveInterest": 3}],
    }]
    flat = _flatten_g4_4_groups(nested)
    assert flat[0]["couponRate"] == 3.0
    restored = _nest_g4_4_flat_rows(flat)
    assert restored[0]["initial"]["couponRate"] == 0.03


def test_g4_freeform_conclusion_prefixes_include_g4():
    """checklist_responses 应对 G4- JSON conclusion 跳过 Y/N 白名单。"""
    import inspect
    from app.routers import checklist_responses as mod

    src = inspect.getsource(mod)
    assert '"G4-"' in src or "'G4-'" in src
    assert "G4A-" in src
