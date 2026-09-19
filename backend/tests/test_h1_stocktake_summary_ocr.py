"""H1-11 stocktake summary OCR — section schema smoke."""

from app.routers.wp_render_strategies._h1_stocktake_summary_ocr import (
    _SECTION_SCHEMAS,
    _empty_fields,
)


def test_section_schemas_cover_h1_11_modes():
    assert set(_SECTION_SCHEMAS) == {
        "location", "precheck", "building", "recount", "narrative",
        "client-plan", "plan-narrative",
    }


def test_empty_fields_numeric_defaults():
    loc = _empty_fields("location")
    assert loc["assetName"] == ""
    recount = _empty_fields("recount")
    assert recount["recountTotalUnits"] == 0
    assert recount["recountPersonnel"] == ""
    client = _empty_fields("client-plan")
    assert client["icSystemName"] == ""
    assert client["content"] == ""
