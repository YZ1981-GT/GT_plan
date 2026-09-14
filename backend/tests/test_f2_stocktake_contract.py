"""F2 监盘 bundle 注册契约 + 导入导出 header 对齐."""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.routers.wp_render_strategies._f2_stocktake_import_export import _F2_ST_SPECS
from app.routers.wp_render_strategies._cycle_import_export_common import parse_upload_xlsx
from app.services.wp_classification_service import VALID_COMPONENT_TYPES
from tests.f_cycle_f2_html_contract import (
    F2_STOCKTAKE,
    F2_STOCKTAKE_CODES,
    expected_f2_component_type,
)

_ROOT = Path(__file__).resolve().parents[1]
_WP_OVERRIDES = _ROOT / "app" / "data" / "wp_code_overrides.json"


def _load_overrides() -> dict[str, str]:
    return json.loads(_WP_OVERRIDES.read_text(encoding="utf-8"))


def test_stocktake_in_valid_component_types():
    assert F2_STOCKTAKE in VALID_COMPONENT_TYPES


def test_wp_overrides_stocktake_codes():
    overrides = _load_overrides()
    for code in F2_STOCKTAKE_CODES:
        assert overrides.get(code) == F2_STOCKTAKE, f"{code} override mismatch"


def test_expected_f2_component_type_stocktake():
    for code in F2_STOCKTAKE_CODES:
        assert expected_f2_component_type(code) == F2_STOCKTAKE


def test_f2_st_specs_headers_align():
    for code, spec in _F2_ST_SPECS.items():
        assert len(spec["headers"]) == len(spec["field_keys"]), code
        assert spec["item_id"] == f"{code}-rows"


def test_f2_st_import_xlsx_parse_f2_24():
    spec = _F2_ST_SPECS["F2-24"]
    wb = Workbook()
    ws = wb.active
    ws.title = "F2-24"
    ws.append(["标题"])
    ws.append(spec["headers"])
    ws.append(["钢材", "10mm", 100, 50000, 98, 49000, ""])
    buf = io.BytesIO()
    wb.save(buf)
    actual, rows = parse_upload_xlsx(buf.getvalue(), spec["headers"], header_row=2)
    assert actual == spec["headers"]
    assert len(rows) >= 1


@pytest.mark.parametrize("sheet", ["F2-21", "F2-22", "F2-23"])
def test_f2_st_specs_exclude_text_sheets(sheet: str):
    assert sheet not in _F2_ST_SPECS
