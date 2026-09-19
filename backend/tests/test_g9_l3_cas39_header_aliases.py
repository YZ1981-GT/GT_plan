"""G9-5 CAS39 纸质列名 → 十因子电子稿 header_aliases 单测."""

from app.routers.wp_render_strategies._cycle_import_export_common import apply_header_aliases
from app.routers.wp_render_strategies._g9_other_noncurrent_financial_import_export import (
    _G9_5_HEADER_ALIASES,
    _G9_SPECS,
)


def test_g9_5_spec_allows_missing_headers_and_aliases():
    sp = _G9_SPECS["G9-5"]
    assert sp.get("allow_missing_headers") is True
    assert "header_aliases" in sp
    assert "资产名称" in sp["header_aliases"]


def test_cas39_headers_map_to_ten_factor_canonical():
    cas39 = [
        "投资项目",
        "期初余额",
        "转入第三层次",
        "转出第三层次",
        "公允价值变动损益",
        "投资收益",
        "购买",
        "发行",
        "出售",
        "结算",
        "期末余额",
        "仍持有未实现损益变动",
    ]
    mapped = apply_header_aliases(cas39, _G9_5_HEADER_ALIASES)
    assert "资产名称" in mapped
    assert "期初公允价值" in mapped
    assert "本期购入" in mapped
    assert "本期处置" in mapped
    assert "利息收入" in mapped
    assert "其他变动" in mapped  # 发行 / 结算
    assert "期末公允价值" in mapped
    assert "仍持有未实现" in mapped


def test_canonical_headers_unchanged():
    canonical = ["资产名称", "期初公允价值", "本期购入", "公允价值变动OCI"]
    assert apply_header_aliases(canonical, _G9_5_HEADER_ALIASES) == canonical
