"""F2 import/export round-trip unit tests (template headers + parse)."""

from __future__ import annotations

import io

from openpyxl import Workbook

from app.routers.wp_render_strategies._f2_import_export import _headers, _parse_f2_row, _sheet_kind
from app.routers.wp_render_strategies._f2_valuation_import_export import _F2_VAL_SPECS
from app.routers.wp_render_strategies._f2_special_import_export import _F2_SPE_SPECS
from app.routers.wp_render_strategies._cycle_import_export_common import parse_upload_xlsx


def _build_xlsx(sheet: str, headers: list[str], data_row: list) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(["标题"])
    ws.append(headers)
    ws.append(data_row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_f2_detail_import_parse_roundtrip():
    sheet = "F2-3"
    headers = _headers(sheet)
    row = ("测试品名", 10, 100, 5, 50, 2, 20, 0, 0, 0, 0)
    parsed = _parse_f2_row(sheet, row, headers)
    assert parsed["itemName"] == "测试品名"
    assert parsed["openingQty"] == 10


def test_f2_cutoff_export_field_kind():
    assert _sheet_kind("F2-29") == "cutoff"


def test_f2_valuation_spec_headers_align():
    for code, spec in _F2_VAL_SPECS.items():
        assert len(spec["headers"]) == len(spec["field_keys"]), code


def test_f2_val_import_xlsx_parse():
    spec = _F2_VAL_SPECS["F2-38"]
    content = _build_xlsx(
        "F2-38",
        spec["headers"],
        [1, "记-001", "材料A", 100, 1000, 50, 500, 30, 300, 0, 0, 0, 0, 0],
    )
    actual, rows = parse_upload_xlsx(content, spec["headers"], header_row=2)
    assert len(rows) >= 1
    assert actual == spec["headers"]


def test_f2_special_spec_headers_align():
    for code, spec in _F2_SPE_SPECS.items():
        assert len(spec["headers"]) == len(spec["field_keys"]), code


def test_f2_spe_import_xlsx_parse():
    spec = _F2_SPE_SPECS["F2-61"]
    content = _build_xlsx(
        "F2-61",
        spec["headers"],
        ["钢材A", "10mm", 100.5, 105.2, 102.8, "备注"],
    )
    actual, rows = parse_upload_xlsx(content, spec["headers"], header_row=2)
    assert len(rows) >= 1
    assert actual == spec["headers"]


def test_f2_spe_entity_flat_roundtrip():
    from app.routers.wp_render_strategies._f2_special_import_export import (
        _entities_to_flat,
        _flat_to_entities,
    )

    supplier = [{
        "id": "s1",
        "supplierName": "供应商A",
        "creditCode": "91110000",
        "legalRepresentative": "张三",
        "registeredCapital": "1000万",
        "checkMethod": "实地",
        "checkConclusion": "无异常",
        "cooperationYears": 3,
        "transactionAmount": 500000,
    }]
    flat = _entities_to_flat("F2-70", supplier)
    assert flat[0]["supplierName"] == "供应商A"
    assert flat[0]["id"] == "s1"
    restored = _flat_to_entities("F2-70", flat)
    assert restored[0]["id"] == "s1"
    assert restored[0]["supplierName"] == "供应商A"
    assert restored[0]["transactionAmount"] == 500000

    flat_no_id = [{k: v for k, v in flat[0].items() if k != "id"}]
    restored_new = _flat_to_entities("F2-70", flat_no_id)
    assert restored_new[0]["id"].startswith("imp-")

    interview = [{
        "id": "i1",
        "supplierName": "供应商B",
        "interviewDate": "2025-01-01",
        "interviewee": "李四",
        "topic": "采购真实性",
        "auditFocus": "价格",
        "conclusion": "无异常",
        "qaPairs": [{"id": "q1", "question": "如何定价", "answer": "市场价"}],
    }]
    flat_i = _entities_to_flat("F2-72", interview)
    assert "Q:如何定价" in flat_i[0]["qaSummary"]
    restored_i = _flat_to_entities("F2-72", flat_i)
    assert restored_i[0]["qaPairs"][0]["question"] == "如何定价"


def test_f2_st_spec_headers_align():
    from app.routers.wp_render_strategies._f2_stocktake_import_export import _F2_ST_SPECS

    for code, spec in _F2_ST_SPECS.items():
        assert len(spec["headers"]) == len(spec["field_keys"]), code


def test_f2_st_import_xlsx_parse():
    from app.routers.wp_render_strategies._f2_stocktake_import_export import _F2_ST_SPECS

    spec = _F2_ST_SPECS["F2-24"]
    content = _build_xlsx(
        "F2-24",
        spec["headers"],
        ["钢材", "10mm", 100, 50000, 98, 49000, ""],
    )
    actual, rows = parse_upload_xlsx(content, spec["headers"], header_row=2)
    assert len(rows) >= 1
    assert actual == spec["headers"]
