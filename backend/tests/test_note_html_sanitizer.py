"""Phase 2 Task 11~12 测试：HTML 消毒器与前后端标签一致性。"""

from __future__ import annotations

import pytest

from app.services.note_html_sanitizer import (
    ALLOWED_ATTRS,
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
