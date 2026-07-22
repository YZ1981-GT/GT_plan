"""G10 附注披露 Excel 往返测试."""

from __future__ import annotations

import io

from app.routers.wp_render_strategies._g10_disclosure_io import (
    build_listed_disclosure_workbook,
    build_soe_disclosure_workbook,
    default_listed_store,
    default_soe_store,
    parse_listed_disclosure_workbook,
    parse_soe_disclosure_workbook,
)


def _wb_bytes(wb) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_g10_listed_disclosure_roundtrip():
    store = default_listed_store()
    store["auditYear"] = 2025
    store["movement"]["mv_trading_bond"]["closingAmount"] = 123.45
    store["designatedDetail"]["designated_1"]["designationReason"] = "测试理由"
    wb = build_listed_disclosure_workbook(store)
    fv_hdrs = [wb["信用风险"].cell(1, c).value for c in range(1, 6)]
    assert any(h and "2025年" in str(h) and "公允价值变动" in str(h) for h in fv_hdrs)
    parsed, errors, count = parse_listed_disclosure_workbook(_wb_bytes(wb))
    assert not errors
    assert count >= 5
    assert parsed["movement"]["mv_trading_bond"]["closingAmount"] == 123.45
    assert parsed["designatedDetail"]["designated_1"]["designationReason"] == "测试理由"
    assert parsed.get("auditYear") == 2025


def test_g10_soe_disclosure_roundtrip():
    store = default_soe_store()
    store["balance"]["soe_derivative"]["currentAmount"] = 88.0
    wb = build_soe_disclosure_workbook(store)
    parsed, errors, count = parse_soe_disclosure_workbook(_wb_bytes(wb))
    assert not errors
    assert count >= 4
    assert parsed["balance"]["soe_derivative"]["currentAmount"] == 88.0
