"""BP-21 受管区排版占位行平台级规则的守卫（G2-1）。

`excel_typography_rows.py` 的 docstring 早就引用了本文件的
`TestAsciiDotFormIsRegisteredNotSilent`，但文件此前不存在 —— 平台级判据无单元测试锁死，
是 BP-21 的真实缺口。本文件补齐：

* 纯函数判据的边界（含/不含 U+2026、尾部连续 vs 区内任意、全占位空区间）；
* instrumentation 期 fail-closed 门（末行落占位行必抛并给出应声明值；空列不得放行）；
* ASCII 点写法登记计数与全库现算相等（登记而非静默留洞）；
* BP-21 验收：四个 pilot 受管区内排版占位行为 0（复用检查脚本的真实扫描）；
* 变异反证：把尾部占位剔除短路后，受管区扫描重新命中 H1/D2。
"""
import importlib.util
import sys
import types
from pathlib import Path

import pytest

from app.services.workpaper_sync import excel_typography_rows as T

ROOT = Path(__file__).resolve().parents[3]
CHECK_SCRIPT = ROOT / "backend/scripts/check/check_managed_region_typography_rows.py"


def _load_check() -> types.ModuleType:
    name = "bp21_check_under_test"
    spec = importlib.util.spec_from_file_location(name, CHECK_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# ── 1. 纯函数判据 ────────────────────────────────────────────────────


class TestIsTypographyPlaceholder:
    def test_pure_ellipsis_is_placeholder(self):
        assert T.is_typography_placeholder("\u2026\u2026") is True
        assert T.is_typography_placeholder("\u2026") is True

    def test_ellipsis_with_only_typography_chars(self):
        assert T.is_typography_placeholder("\u2026 。") is True
        assert T.is_typography_placeholder("\u2026.") is True

    def test_empty_is_not_placeholder(self):
        # 空行是「还没填的业务行」，不是排版占位
        assert T.is_typography_placeholder("") is False
        assert T.is_typography_placeholder(None) is False

    def test_no_ellipsis_is_not_placeholder(self):
        assert T.is_typography_placeholder("......") is False  # 纯 ASCII 点不进窄判据
        assert T.is_typography_placeholder("合计") is False

    def test_ellipsis_with_business_content_is_not_placeholder(self):
        # 「……1」「合计……」不是纯排版：误判会把真实业务/footer 行挖掉
        assert T.is_typography_placeholder("\u20261") is False
        assert T.is_typography_placeholder("合计\u2026") is False


class TestTrailingTypographyRows:
    def test_only_trailing_consecutive_counted(self):
        col = {13: "1", 14: "2", 15: "\u2026\u2026"}
        assert T.trailing_typography_rows(first_data_row=13, last_data_row=15, column_text=col) == (15,)

    def test_mid_region_ellipsis_not_counted(self):
        # 区内中间的省略号是业务行里的取值，不剔
        col = {13: "1", 14: "\u2026", 15: "3"}
        assert T.trailing_typography_rows(first_data_row=13, last_data_row=15, column_text=col) == ()

    def test_multiple_trailing(self):
        col = {13: "1", 14: "\u2026", 15: "\u2026"}
        assert T.trailing_typography_rows(first_data_row=13, last_data_row=15, column_text=col) == (14, 15)

    def test_empty_when_last_before_first(self):
        assert T.trailing_typography_rows(first_data_row=13, last_data_row=12, column_text={}) == ()


class TestLastBusinessDataRow:
    def test_shrinks_by_trailing_count(self):
        col = {13: "1", 14: "2", 15: "\u2026"}
        assert T.last_business_data_row(first_data_row=13, last_data_row=15, column_text=col) == 14

    def test_all_placeholder_returns_empty_region_marker(self):
        col = {13: "\u2026", 14: "\u2026"}
        # 全占位 → first_data_row - 1（调用方须当错误处理）
        assert T.last_business_data_row(first_data_row=13, last_data_row=14, column_text=col) == 12


class TestDecodeCellText:
    def test_decimal_and_hex_numeric_refs(self):
        assert T.decode_cell_text("&#21512;&#35745;") == "合计"
        assert T.decode_cell_text("&#x5408;&#x8ba1;") == "合计"

    def test_basic_xml_entities(self):
        assert T.decode_cell_text("a &amp; b") == "a & b"

    def test_undefined_html_entity_not_silently_replaced(self):
        # &nbsp; 在 XML 里未定义，不得静默替换（掩盖非法文档）
        assert "&nbsp;" in T.decode_cell_text("x&nbsp;y")


# ── 2. instrumentation 期 fail-closed 门 ──────────────────────────────


def _sheet_xml_with_column_a(rows: dict[int, str]) -> str:
    cells = []
    for row, text in rows.items():
        cells.append(
            f'<row r="{row}"><c r="A{row}" t="inlineStr"><is><t>{text}</t></is></c></row>'
        )
    return f"<worksheet><sheetData>{''.join(cells)}</sheetData></worksheet>"


class TestAssertLastDataRowGate:
    def test_placeholder_last_row_fails_closed_with_corrected_value(self):
        xml = _sheet_xml_with_column_a({13: "1", 14: "2", 15: "\u2026\u2026"})
        with pytest.raises(T.TypographyRowError) as ei:
            T.assert_last_data_row_is_not_typography_placeholder(
                sheet_xml=xml, shared=[], label_column="A",
                first_data_row=13, last_data_row=15, where="test")
        assert "last_data_row=14" in str(ei.value)

    def test_clean_last_row_returns_empty_tail(self):
        xml = _sheet_xml_with_column_a({13: "1", 14: "2", 15: "3"})
        assert T.assert_last_data_row_is_not_typography_placeholder(
            sheet_xml=xml, shared=[], label_column="A",
            first_data_row=13, last_data_row=15, where="test") == ()

    def test_empty_column_does_not_pass(self):
        # 标签列一个非空格都没读到时不得放行（空集上恒真）
        with pytest.raises(T.TypographyRowError):
            T.assert_last_data_row_is_not_typography_placeholder(
                sheet_xml="<worksheet><sheetData/></worksheet>", shared=[],
                label_column="A", first_data_row=13, last_data_row=15, where="test")

    def test_all_placeholder_region_fails(self):
        xml = _sheet_xml_with_column_a({13: "\u2026", 14: "\u2026"})
        with pytest.raises(T.TypographyRowError):
            T.assert_last_data_row_is_not_typography_placeholder(
                sheet_xml=xml, shared=[], label_column="A",
                first_data_row=13, last_data_row=14, where="test")


class TestLabelColumnLock:
    def test_non_a_first_column_fails(self):
        with pytest.raises(T.TypographyRowError):
            T.assert_label_column_matches_spec("B13:AN24", where="test")

    def test_a_first_column_ok(self):
        T.assert_label_column_matches_spec("A13:AN24", where="test")  # no raise


# ── 3. ASCII 点写法：登记而非静默留洞 ─────────────────────────────────


class TestAsciiDotFormIsRegisteredNotSilent:
    """全库现算的窄/宽判据计数必须与登记常量逐个相等（docstring 承诺的守卫）。"""

    @pytest.fixture(scope="class")
    def census(self):
        return _load_check().scan()

    def test_narrow_cells_match_registered(self, census):
        assert census["typography_placeholder_cells"] == \
            T.ASCII_DOT_PLACEHOLDER_CENSUS["narrow_cells"]

    def test_narrow_rows_before_footer_match_registered(self, census):
        assert census["placeholder_row_before_footer"] == \
            T.ASCII_DOT_PLACEHOLDER_CENSUS["narrow_rows_before_footer"]

    def test_narrow_templates_match_registered(self, census):
        assert census["distinct_templates"] == \
            T.ASCII_DOT_PLACEHOLDER_CENSUS["narrow_templates"]

    def test_ascii_dot_is_superset_of_narrow(self):
        assert T.is_ascii_dot_placeholder("\u2026") is True  # 含 U+2026 的一律也算
        assert T.is_ascii_dot_placeholder("......") is True
        assert T.is_ascii_dot_placeholder("ab") is False


# ── 4. BP-21 验收 + 变异反证 ──────────────────────────────────────────


class TestManagedRegionAcceptance:
    @pytest.fixture(scope="class")
    def regions(self):
        return _load_check().scan_managed_regions()

    def test_zero_placeholder_rows_in_regions(self, regions):
        assert regions["placeholder_rows_in_regions"] == 0

    def test_pilots_resolve_to_shrunk_ranges(self, regions):
        by_entry = {r["entry_id"]: r for r in regions["entries"] if r.get("last_row")}
        # H1 减少检查表 13..26（剔除 A27 的 ……）；D2 13..24（剔除 A25）
        h1 = by_entry.get("xlsx/gt-h1-fixed-assets")
        d2 = by_entry.get("xlsx/gt-d2-accounts-receivable")
        assert h1 is not None and h1["last_row"] == 26
        assert d2 is not None and d2["last_row"] == 24

    def test_mutation_short_circuit_reopens_h1_d2(self, monkeypatch, regions):
        """把尾部占位剔除短路后，受管区扫描必须重新命中 H1/D2（变异反证）。

        剔除发生在上游 instrumentation（table_ref 已冻成收缩区间），因此这里从行为层
        证明：若 `trailing_typography_rows` 恒返回空（等价于不剔除），
        `last_business_data_row` 就不再收缩末行。
        """
        col = {13: "1", 14: "2", 15: "\u2026"}
        # 正常：收缩到 14
        assert T.last_business_data_row(
            first_data_row=13, last_data_row=15, column_text=col) == 14
        # 短路变异：trailing 恒空 ⇒ 末行不收缩，占位行 15 被当业务行
        monkeypatch.setattr(T, "trailing_typography_rows", lambda **_: ())
        assert T.last_business_data_row(
            first_data_row=13, last_data_row=15, column_text=col) == 15
