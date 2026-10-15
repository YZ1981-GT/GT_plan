"""纯文字正文进批量写入：先按编辑器口径转 HTML（第 19 组，Task 55 真实写入验收发现）。

真库多数章节 ``text_content`` 是纯文字（生成链写入，含换行、markdown 表格 / 列表），编辑器按
``marked(gfm, breaks)`` 渲染（``DisclosureEditor.renderNoteTextToHtml``）。批量写入首版把纯文字当 HTML：
- 追加：``append_note_html`` 直接拼接 ⇒ 存成「纯文字 + <p>…</p>」混合值，原有分段在差异预览与 Word 里都并成一段；
- 引用模板：纯文字来源写入后差异预览里也并成一段；
- 消毒器把裸 ``&`` 当实体：``R&D`` → ``R&D;``（可见乱码）。
"""

from __future__ import annotations

import uuid

import pytest

from app.services.note_html_sanitizer import append_note_html, note_text_to_html, sanitize_note_html

PLAIN = "第一段第一行\n第一段第二行\n\n第二段"
MD_TABLE = "现金构成如下：\n\n| 项目 | 金额（元） |\n| :--- | :--- |\n| 库存现金 | 1,000.00 |\n\n附注说明：\n\n1. 定义范围\n2. 受限资金"


class TestNoteTextToHtml:
    def test_paragraphs_and_line_breaks_follow_editor(self):
        assert note_text_to_html(PLAIN) == "<p>第一段第一行<br />第一段第二行</p><p>第二段</p>"

    def test_markdown_table_renders_and_typed_numbering_is_text(self):
        html = note_text_to_html(MD_TABLE)
        assert "<table>" in html and "<th>项目</th>" in html and "<td>库存现金</td>" in html
        assert "<p>1. 定义范围<br />2. 受限资金</p>" in html
        assert "|" not in html and "style=" not in html

    def test_typed_numbering_is_never_renumbered(self):
        """第 22 组真库实测：按 markdown 有序列表解释会重排书写的编号 —— 真库 476 个带编号的纯文字章节里
        69 个被改号（如「1~4、1~4」排成 1~8），续编号还丢 start。纯文字里的编号是正文，原样保留。"""
        assert note_text_to_html("1. 甲\n2. 乙\n3. 丙\n1. 丁\n2. 戊") == "<p>1. 甲<br />2. 乙<br />3. 丙<br />1. 丁<br />2. 戊</p>"
        assert note_text_to_html("1. 存货分类\n\n说明段落\n\n2. 计价方法") == "<p>1. 存货分类</p><p>说明段落</p><p>2. 计价方法</p>"
        assert note_text_to_html("- 先进先出\n- 加权平均") == "<p>- 先进先出<br />- 加权平均</p>"

    def test_indented_lines_are_text_not_code_block(self):
        """缩进四格在 markdown 里是代码块（消毒器不认 pre/code ⇒ 剥标签后几行并成一行）；附注正文里只是缩进。"""
        assert note_text_to_html("前文\n\n    缩进四格的一段\n    第二行") == "<p>前文</p><p>缩进四格的一段<br />第二行</p>"

    def test_angle_brackets_and_ampersands_are_text(self):
        assert note_text_to_html("<公司名称> 与 R&D、P&L 1<2") == "<p>&lt;公司名称&gt; 与 R&amp;D、P&amp;L 1&lt;2</p>"

    def test_unknown_markup_in_plain_text_stays_text(self):
        """纯文字里的其它尖括号片段按文字保留（不解释成标签，也不被消毒器连字带标签删掉）。"""
        assert note_text_to_html("见附图 <img src=x> 与 <font>注意</font>") == (
            "<p>见附图 &lt;img src=x&gt; 与 &lt;font&gt;注意&lt;/font&gt;</p>")

    def test_html_input_only_sanitized(self):
        assert note_text_to_html("<p>甲</p><script>x</script>") == "<p>甲</p>"
        assert note_text_to_html("") == "" and note_text_to_html(None) == ""

    def test_idempotent(self):
        for text in (PLAIN, MD_TABLE, "<p>甲</p>"):
            once = note_text_to_html(text)
            assert note_text_to_html(once) == once


class TestAppendToPlainText:
    def test_existing_paragraphs_are_kept(self):
        assert append_note_html(PLAIN, "<p>新</p>") == (
            "<p>第一段第一行<br />第一段第二行</p><p>第二段</p><p>&nbsp;</p><p>新</p>")

    def test_existing_markdown_table_is_kept_as_table(self):
        out = append_note_html(MD_TABLE, "<p>新</p>")
        assert "<table>" in out and out.endswith("<p>&nbsp;</p><p>新</p>")

    def test_dedupe_against_converted_existing(self):
        assert append_note_html("甲\n\n乙", "<p>乙</p><p>丙</p>") == "<p>甲</p><p>乙</p><p>&nbsp;</p><p>丙</p>"

    def test_plain_new_text_is_converted_too(self):
        assert append_note_html("<p>旧</p>", "新一\n\n新二") == "<p>旧</p><p>&nbsp;</p><p>新一</p><p>新二</p>"


class TestSanitizerAmpersand:
    @pytest.mark.parametrize("raw,expected", [
        ("<p>研发（R&D）与 P&L、AT&T</p>", "<p>研发（R&amp;D）与 P&amp;L、AT&amp;T</p>"),
        ("<p>a&b=c</p>", "<p>a&amp;b=c</p>"),
        ("<p>&nbsp;&amp;&lt;&gt;&copy;&#20013;&#x4e2d;</p>", "<p>&nbsp;&amp;&lt;&gt;&copy;&#20013;&#x4e2d;</p>"),
        ("<p>&nbsp</p>", "<p>&nbsp;</p>"),  # 已知实体缺分号：与浏览器一致按实体
    ])
    def test_bare_ampersand_is_text_known_entities_kept(self, raw, expected):
        assert sanitize_note_html(raw) == expected
        assert sanitize_note_html(expected) == expected


class TestPreviewWithPlainText:
    def _preview(self, src_html: str, target_text: str):
        from app.services.note_document_parser import ParsedSection
        from app.services.note_text_batch_service import (
            MatchResult,
            SourceContext,
            build_preview,
            sha256_text,
        )

        tid = uuid.uuid4()
        source = ParsedSection(source_id="s1", title="会计期间", html=src_html,
                               metadata={"note_section": "四、会计期间", "section_kind": "narrative", "status": "confirmed"})
        target = {"id": tid, "note_section": "四、会计期间", "section_title": "会计期间", "section_kind": "narrative",
                  "text_content": target_text, "content_hash": sha256_text(target_text), "updated_at": None}
        match = MatchResult("s1", tid, "same_template_code", "同模板章节编号", "confirmed")
        preview = build_preview([source], [target], [match], source_context=SourceContext(
            kind="content_template", template_type="soe", report_scope="standalone"),
            target_template_type="soe", target_report_scope="standalone")
        return preview["items"][0], sha256_text(target_text)

    def test_plain_template_source_is_written_as_html(self):
        item, _ = self._preview("本公司会计期间为公历年度。\n\n自1月1日起至12月31日止。", "")
        assert item["proposed_html"] == "<p>本公司会计期间为公历年度。</p><p>自1月1日起至12月31日止。</p>"

    def test_append_onto_plain_target_keeps_paragraphs(self):
        item, raw_hash = self._preview("<p>新增说明。</p>", "旧一\n\n旧二")
        assert item["append_html"] == "<p>旧一</p><p>旧二</p><p>&nbsp;</p><p>新增说明。</p>"
        assert item["before_hash"] == raw_hash, "写入前复核按库里原文，不按转换后的显示值"
        assert item["before_html"] == "<p>旧一</p><p>旧二</p>", "差异预览「现有内容」按编辑器口径显示"
