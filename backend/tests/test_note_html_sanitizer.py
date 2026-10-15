"""Phase 2 Task 11~12 测试：HTML 消毒器与前后端标签一致性。"""

from __future__ import annotations

import pytest

from app.services.note_html_sanitizer import (
    ALLOWED_TAGS,
    sanitize_note_html,
)


class TestSanitizeBasic:
    def test_empty_string(self):
        assert sanitize_note_html("") == ""

    def test_none_equivalent(self):
        assert sanitize_note_html("") == ""

    def test_plain_text_escaped(self):
        assert sanitize_note_html("a < b & c") == "a &lt; b &amp; c"

    def test_allowed_tags_preserved(self):
        html = "<p>段落</p><strong>加粗</strong><em>斜体</em>"
        result = sanitize_note_html(html)
        assert "<p>" in result
        assert "<strong>" in result
        assert "<em>" in result

    def test_table_structure_preserved(self):
        html = '<table><tr><td colspan="2">单元格</td></tr></table>'
        result = sanitize_note_html(html)
        assert '<td colspan="2">' in result

    def test_list_preserved(self):
        html = "<ul><li>项目一</li><li>项目二</li></ul>"
        result = sanitize_note_html(html)
        assert "<ul>" in result
        assert "<li>" in result


class TestSanitizeDangerous:
    def test_script_removed(self):
        html = "<p>正文</p><script>alert(1)</script><p>继续</p>"
        result = sanitize_note_html(html)
        assert "script" not in result.lower()
        assert "alert" not in result

    def test_iframe_removed(self):
        html = '<iframe src="evil.html"></iframe>'
        result = sanitize_note_html(html)
        assert "iframe" not in result.lower()

    def test_onerror_removed(self):
        html = '<p onerror="alert(1)">段落</p>'
        result = sanitize_note_html(html)
        assert "onerror" not in result

    def test_style_attribute_removed(self):
        html = '<p style="color:red">红色</p>'
        result = sanitize_note_html(html)
        assert "style" not in result

    def test_javascript_url_removed(self):
        # a 标签本身不在后端白名单
        html = '<a href="javascript:alert(1)">链接</a>'
        result = sanitize_note_html(html)
        assert "javascript" not in result.lower()
        assert "href" not in result

    def test_class_only_whitelist_values(self):
        html = '<span class="gt-note-placeholder">占位</span><span class="evil">恶意</span>'
        result = sanitize_note_html(html)
        assert 'class="gt-note-placeholder"' in result
        assert "evil" not in result

    def test_object_embed_removed(self):
        html = '<object data="x"></object><embed src="y" />'
        result = sanitize_note_html(html)
        assert "object" not in result.lower()
        assert "embed" not in result.lower()


class TestSanitizeIdempotent:
    @pytest.mark.parametrize("html", [
        "<p>正常段落</p>",
        '<table><tr><td colspan="2">表格</td></tr></table>',
        '<span class="gt-note-placeholder">占位</span>',
        "<ul><li>列表</li></ul>",
        "纯文本 < & >",
    ])
    def test_idempotent(self, html: str):
        first = sanitize_note_html(html)
        second = sanitize_note_html(first)
        assert first == second, f"消毒不幂等：\nfirst:  {first}\nsecond: {second}"


class TestFrontendBackendConsistency:
    """后端白名单是前端 ALLOWED_TAGS 的严格子集（后端更严格）。"""

    def test_backend_tags_subset_of_frontend(self):
        # 前端白名单（从 useSanitize.ts 复制）
        frontend_tags = {
            "h1", "h2", "h3", "h4", "h5", "h6",
            "ul", "ol", "li",
            "table", "thead", "tbody", "tr", "td", "th",
            "strong", "em", "br", "p", "span",
            "pre", "code", "blockquote",
            "a", "del", "hr", "dl", "dt", "dd",
        }
        # 后端允许的标签都必须在前端名单中（否则后端放行前端却剥离 = 数据丢失）
        backend_only = ALLOWED_TAGS - frontend_tags
        assert not backend_only, f"后端允许但前端不允许的标签: {backend_only}"

    def test_backend_stricter_than_frontend(self):
        """后端确实不允许 a/pre/code/del/dl/dt/dd（前端允许但后端不允许）。"""
        frontend_only = {"a", "pre", "code", "del", "dl", "dt", "dd", "h6"}
        for tag in frontend_only:
            assert tag not in ALLOWED_TAGS, f"后端不应允许 {tag}"

    def test_layout_attrs_survive_frontend_display_sanitizer(self):
        """影响版面的属性（合并单元格、列表起始编号）前端展示消毒也必须放行，否则差异预览与写入结果不一致。

        读真实的 ``useSanitize.ts``（不抄副本）：第 22 组加 ``ol start`` 时前端名单漏了它，预览里续编号会从 1 开始。
        """
        import re
        from pathlib import Path

        source = (Path(__file__).resolve().parents[2] / "audit-platform/frontend/src/composables/useSanitize.ts"
                  ).read_text(encoding="utf-8")
        block = re.search(r"const ALLOWED_ATTR = \[(.*?)\]", source, re.S)
        assert block, "useSanitize.ts 里找不到 ALLOWED_ATTR"
        frontend_attrs = set(re.findall(r"'([\w-]+)'", block.group(1)))
        assert {"colspan", "rowspan", "start"} <= frontend_attrs


class TestOrderedListStart:
    """第 22 组：续编号列表（「2. …」，真库 3 个项目共 571 处）消毒后不能丢起始编号，否则写入后从 1 重新编号。"""

    @pytest.mark.parametrize(("html", "expected"), [
        ('<ol start="2"><li>甲</li></ol>', '<ol start="2"><li>甲</li></ol>'),
        ('<ol start="0"><li>甲</li></ol>', "<ol><li>甲</li></ol>"),
        ('<ol start="x"><li>甲</li></ol>', "<ol><li>甲</li></ol>"),
        ('<ol start="10000"><li>甲</li></ol>', "<ol><li>甲</li></ol>"),
        ('<ul start="2"><li>甲</li></ul>', "<ul><li>甲</li></ul>"),
    ])
    def test_start_kept_only_when_valid(self, html: str, expected: str):
        assert sanitize_note_html(html) == expected
        assert sanitize_note_html(expected) == expected

    def test_plain_text_numbering_continues_after_conversion(self):
        from app.services.note_html_sanitizer import note_text_to_html

        assert note_text_to_html("1. 存货分类\n\n说明段落\n\n2. 计价方法") == (
            '<ol><li>存货分类</li></ol><p>说明段落</p><ol start="2"><li>计价方法</li></ol>')


# ── 第二轮复盘 R-05：未知标签只剥标签、保留文本；危险容器才丢内容 ──────────────


class TestUnknownTagsKeepText:
    """复盘探针实测：首版把所有非白名单标签的内容整段吞掉，<img> 还会吞掉其后全部正文。"""

    def test_void_unknown_tag_does_not_swallow_following_content(self):
        result = sanitize_note_html('<p>甲</p><img src="x.png"><p>乙</p>')
        assert result == "<p>甲</p><p>乙</p>"

    def test_div_wrapper_keeps_inner_paragraph(self):
        assert sanitize_note_html("<div><p>正文</p></div>") == "<p>正文</p>"

    @pytest.mark.parametrize("html,expected", [
        ("<p>注<sup>1</sup>说明</p>", "<p>注1说明</p>"),
        ("<p><u>下划线</u>文字</p>", "<p>下划线文字</p>"),
        ('<p><a href="https://x">链接</a>后文</p>', "<p>链接后文</p>"),
    ])
    def test_inline_unknown_tags_keep_text(self, html: str, expected: str):
        assert sanitize_note_html(html) == expected

    def test_b_and_i_map_to_strong_and_em(self):
        assert sanitize_note_html("<b>粗</b><i>斜</i>") == "<strong>粗</strong><em>斜</em>"

    @pytest.mark.parametrize("html", [
        "<style>p{color:red}</style><p>正文</p>",
        "<iframe><p>框内</p></iframe><p>正文</p>",
        "<object><p>框内</p></object><p>正文</p>",
        "<noscript><p>框内</p></noscript><p>正文</p>",
    ])
    def test_dangerous_containers_drop_content(self, html: str):
        assert sanitize_note_html(html) == "<p>正文</p>"

    def test_void_dangerous_tag_does_not_swallow_following_content(self):
        """embed 既是危险容器又是 void：若漏出 void 集合，深度永不回落 ⇒ 后文被吞。"""
        assert sanitize_note_html('<p>前</p><embed src="x"><p>后</p>') == "<p>前</p><p>后</p>"

    def test_span_numeric_attrs_validated(self):
        assert sanitize_note_html('<table><tr><td colspan="3">a</td></tr></table>') == (
            '<table><tr><td colspan="3">a</td></tr></table>'
        )
        assert "colspan" not in sanitize_note_html('<table><tr><td colspan="2;x">a</td></tr></table>')

    @pytest.mark.parametrize("html", [
        '<p>甲</p><img src="x.png"><p>乙</p>',
        "<div><p>正文</p></div>",
        "<b>粗</b><i>斜</i>",
    ])
    def test_new_paths_idempotent(self, html: str):
        once = sanitize_note_html(html)
        assert sanitize_note_html(once) == once


class TestSplitTopLevelBlocks:
    def test_splits_blocks_and_top_level_text(self):
        from app.services.note_html_sanitizer import split_top_level_blocks

        assert split_top_level_blocks("<p>a</p><ul><li>b</li></ul>c") == [
            "<p>a</p>", "<ul><li>b</li></ul>", "c",
        ]

    def test_blocks_are_canonical(self):
        from app.services.note_html_sanitizer import split_top_level_blocks

        assert split_top_level_blocks("<P>a</P><b>x</b>") == ["<p>a</p>", "<strong>x</strong>"]


def test_append_sanitizes_existing_side_too() -> None:
    """第 7 组整体复盘（Task 12 变异）：去掉对现有正文的消毒，首版没有任何测试发现。

    现有正文来自库里其他写入方，追加时整段重写回库，不能把其中的危险标签原样带回去。
    """
    from app.services.note_html_sanitizer import append_note_html

    out = append_note_html('<p>旧一</p><script>alert(1)</script><p onclick="x()">旧二</p>', "<p>新</p>")
    assert "<script" not in out and "onclick" not in out
    assert all(t in out for t in ("旧一", "旧二", "新"))
