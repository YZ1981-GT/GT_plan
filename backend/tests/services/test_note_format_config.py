"""Sprint 4 Task 4.4 — NoteFormatConfig (致同 21 项排版规范) 单测.

Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 4 Task 4.4
Reqs:   v2 §5.4 / R5.2 — 21 项排版参数 dataclass + 端点 + CSS 变量映射

覆盖：
1. dataclass(frozen=True) 不可变性
2. 21 个字段名全部存在（CI 卡点）
3. 端点返回 schema 完整
4. ``to_css_variables`` 映射覆盖每个字段（21 → 至少 21 个 CSS 变量）
5. 默认值与致同 PDF 来源（margin_top=3.2 / 仿宋_GB2312 / Arial Narrow / 1磅 / 0.5磅 / 0.7cm）一致
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.services.note_format_config import (
    DEFAULT_GT_FORMAT,
    NoteFormatConfig,
)


# ---------------------------------------------------------------------------
# 1. dataclass 不可变性
# ---------------------------------------------------------------------------


class TestFrozenDataclass:
    def test_default_instance_exists(self):
        assert isinstance(DEFAULT_GT_FORMAT, NoteFormatConfig)

    def test_cannot_mutate_field(self):
        with pytest.raises(FrozenInstanceError):
            DEFAULT_GT_FORMAT.margin_top_cm = 99.0  # type: ignore[misc]

    def test_cannot_assign_new_attribute(self):
        with pytest.raises(FrozenInstanceError):
            DEFAULT_GT_FORMAT.new_field = "foo"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# 2. 21 项字段必检（CI 卡点）
# ---------------------------------------------------------------------------


REQUIRED_FIELDS_21 = [
    # 页面设置（4）
    "margin_top_cm",
    "margin_bottom_cm",
    "margin_left_cm",
    "margin_right_cm",
    # 页眉页脚（2）
    "header_distance_cm",
    "footer_distance_cm",
    # 字体（4）
    "font_chinese",
    "font_western",
    "font_size_pt",
    "font_size_table_pt",
    # 段落间距（4）
    "heading_space_after_lines",
    "body_space_after_lines",
    "after_table_space_before_lines",
    "after_table_space_after_lines",
    # 表格（4）
    "table_top_border_pt",
    "table_bottom_border_pt",
    "header_bottom_border_pt",
    "table_row_height_cm",
    # 标题缩进（2）
    "heading1_left_indent_chars",
    "heading2_left_indent_chars",
    # 数值格式（1）
    "empty_value_placeholder",
]


class TestFieldCoverage:
    def test_field_count_is_exactly_21(self):
        names = NoteFormatConfig.field_names()
        assert len(names) == 21, (
            f"NoteFormatConfig 必须严格 21 项，当前 {len(names)} 项: {names}"
        )

    def test_all_required_fields_present(self):
        names = NoteFormatConfig.field_names()
        missing = [f for f in REQUIRED_FIELDS_21 if f not in names]
        assert not missing, f"缺字段: {missing}"

    def test_no_unauthorized_fields(self):
        names = NoteFormatConfig.field_names()
        extra = [f for f in names if f not in REQUIRED_FIELDS_21]
        assert not extra, f"含未授权字段: {extra}"


# ---------------------------------------------------------------------------
# 3. 默认值匹配致同 PDF 来源
# ---------------------------------------------------------------------------


class TestDefaultValuesMatchGTSource:
    """默认值必须严格匹配 ``附注模版/上市报表附注.md`` + ``国企报表附注.md`` 头部使用说明."""

    def test_page_margins_match_gt_spec(self):
        # 「①页边距：左3、右3.18、上3.2、下2.54」
        assert DEFAULT_GT_FORMAT.margin_top_cm == 3.2
        assert DEFAULT_GT_FORMAT.margin_bottom_cm == 2.54
        assert DEFAULT_GT_FORMAT.margin_left_cm == 3.0
        assert DEFAULT_GT_FORMAT.margin_right_cm == 3.18

    def test_header_footer_distance(self):
        # 「②版式：页眉1.3、页脚1.3」
        assert DEFAULT_GT_FORMAT.header_distance_cm == 1.3
        assert DEFAULT_GT_FORMAT.footer_distance_cm == 1.3

    def test_font_chinese_is_fangsong(self):
        # 「中文：仿宋_GB2312、小四」
        assert DEFAULT_GT_FORMAT.font_chinese == "仿宋_GB2312"

    def test_font_western_is_arial_narrow(self):
        # 「数字或英文：Arial Narrow」
        assert DEFAULT_GT_FORMAT.font_western == "Arial Narrow"

    def test_font_size_xiaosi_12pt(self):
        # 小四 = 12pt
        assert DEFAULT_GT_FORMAT.font_size_pt == 12

    def test_table_borders(self):
        # 「④表格边框：上下边框1磅，标题行下边框1/2磅」
        assert DEFAULT_GT_FORMAT.table_top_border_pt == 1.0
        assert DEFAULT_GT_FORMAT.table_bottom_border_pt == 1.0
        assert DEFAULT_GT_FORMAT.header_bottom_border_pt == 0.5

    def test_row_height_xiaosi_07cm(self):
        # 「小四字号下单行行高为0.7」
        assert DEFAULT_GT_FORMAT.table_row_height_cm == 0.7

    def test_heading_indents_negative(self):
        # ADR-009 D7：H1 leftChars=-200 / H2 leftChars=-100
        assert DEFAULT_GT_FORMAT.heading1_left_indent_chars == -2.0
        assert DEFAULT_GT_FORMAT.heading2_left_indent_chars == -1.0

    def test_empty_placeholder_is_blank(self):
        # 「⑩数字格式0或无文字时应留白（不应填写为"0"、"-"、"/"等）」
        assert DEFAULT_GT_FORMAT.empty_value_placeholder == ""


# ---------------------------------------------------------------------------
# 4. to_dict / to_css_variables
# ---------------------------------------------------------------------------


class TestSerializers:
    def test_to_dict_has_21_keys(self):
        d = DEFAULT_GT_FORMAT.to_dict()
        assert len(d) == 21

    def test_to_dict_values_serializable(self):
        """所有字段值必须 JSON-safe (str / int / float)."""
        import json
        d = DEFAULT_GT_FORMAT.to_dict()
        json.dumps(d, ensure_ascii=False)  # 不抛异常即通过

    def test_to_css_variables_covers_each_field(self):
        css = DEFAULT_GT_FORMAT.to_css_variables()
        # 每个字段至少映射到一个 CSS 变量
        assert len(css) >= 21, (
            f"CSS 变量数（{len(css)}) 不足 21 项字段映射"
        )

    def test_css_variables_use_gt_note_prefix(self):
        css = DEFAULT_GT_FORMAT.to_css_variables()
        for name in css:
            assert name.startswith("--gt-note-"), (
                f"CSS 变量必须以 --gt-note- 前缀（ADR-009 GTNote* 命名空间）: {name}"
            )

    def test_css_variables_include_units(self):
        """cm/pt 类字段的 CSS 值必须带单位."""
        css = DEFAULT_GT_FORMAT.to_css_variables()
        assert css["--gt-note-margin-top"].endswith("cm")
        assert css["--gt-note-table-top-border"].endswith("pt")
        assert css["--gt-note-font-size"].endswith("pt")

    def test_css_font_chinese_quoted(self):
        css = DEFAULT_GT_FORMAT.to_css_variables()
        assert css["--gt-note-font-chinese"] == '"仿宋_GB2312"'

    def test_css_font_western_quoted(self):
        css = DEFAULT_GT_FORMAT.to_css_variables()
        assert css["--gt-note-font-western"] == '"Arial Narrow"'


# ---------------------------------------------------------------------------
# 5. 端点
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_format_config_endpoint_returns_complete_schema():
    """``GET /api/disclosure-notes/format-config`` 返回 dict + 21 字段."""
    # 直接调用 router function 避免起 FastAPI server
    from app.routers.disclosure_notes import get_format_config

    # 端点不需要 db / 项目鉴权，仅 current_user
    fake_user = object()
    resp = await get_format_config(current_user=fake_user)  # type: ignore[arg-type]
    assert "format_config" in resp
    assert "css_variables" in resp
    assert resp["field_count"] == 21
    assert len(resp["format_config"]) == 21
    # 抽查一个关键字段
    assert resp["format_config"]["margin_top_cm"] == 3.2
    assert resp["format_config"]["font_chinese"] == "仿宋_GB2312"


@pytest.mark.asyncio
async def test_format_config_endpoint_css_variables_present():
    from app.routers.disclosure_notes import get_format_config

    fake_user = object()
    resp = await get_format_config(current_user=fake_user)  # type: ignore[arg-type]
    css = resp["css_variables"]
    assert isinstance(css, dict)
    assert len(css) >= 21
    # 抽查若干关键 CSS 变量
    assert "--gt-note-margin-top" in css
    assert "--gt-note-font-size" in css
    assert "--gt-note-table-top-border" in css
