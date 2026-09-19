"""cycle import/export 公共工具：表头别名与按名解析."""
from app.routers.wp_render_strategies._cycle_import_export_common import (
    apply_header_aliases,
    parse_row_by_headers,
)


def test_apply_header_aliases_normalizes_old_names():
    actual = ["序号", "被投资方", "企业入账金额", "测算差异"]
    out = apply_header_aliases(actual, {"账面已计股利": ["企业入账金额"]})
    assert out == ["序号", "被投资方", "账面已计股利", "测算差异"]


def test_parse_row_by_headers_name_based_ignores_order_and_missing():
    expected = ["序号", "被投资方", "账面已计股利", "本期减少"]
    keys = ["seq", "investeeName", "bookedAmount", "periodDecrease"]
    # 打乱顺序 + 旧列名已由上层别名归一；缺少本期减少
    actual = ["被投资方", "账面已计股利", "序号"]
    row = ("甲公司", 1200, 1)
    parsed = parse_row_by_headers(
        row, actual, keys, expected_headers=expected,
    )
    assert parsed["seq"] == 1.0
    assert parsed["investeeName"] == "甲公司"
    assert parsed["bookedAmount"] == 1200.0
    assert parsed["periodDecrease"] == 0.0  # 缺列 → numeric 空


def test_parse_row_by_headers_positional_legacy_still_works():
    headers = ["a", "b"]
    keys = ["seq", "investeeName"]
    parsed = parse_row_by_headers((1, "乙"), headers, keys)
    assert parsed["seq"] == 1.0
    assert parsed["investeeName"] == "乙"
