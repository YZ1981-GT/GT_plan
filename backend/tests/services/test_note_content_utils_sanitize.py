"""sanitize_note_narrative 测试（spec disclosure-note-quality-completion R1 / Property 1）。

markdown 源头止血纯函数：幂等 + 输出不含 ###/裸 ** markdown 标记 + HTML 原样。
"""
from __future__ import annotations

import re

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.note_content_utils import sanitize_note_narrative

_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_BOLD = re.compile(r"(\*\*|__).+?\1", re.DOTALL)


def test_empty_and_none():
    assert sanitize_note_narrative(None) == ""
    assert sanitize_note_narrative("") == ""
    assert sanitize_note_narrative("   ") == ""


def test_strips_heading_marker():
    out = sanitize_note_narrative("### 五、4 应收票据\n正文内容")
    assert "###" not in out
    assert "五、4 应收票据" in out
    assert "正文内容" in out


def test_strips_bold():
    out = sanitize_note_narrative("**[需补充信息提示]** 期末余额如下")
    assert "**" not in out
    assert "[需补充信息提示]" in out
    assert "期末余额如下" in out


def test_strips_list_and_link_and_code():
    out = sanitize_note_narrative("- 第一项\n- 第二项\n见 [附注五](x) 及 `TB(1121)`")
    assert not _HEADING.search(out)
    assert "第一项" in out and "第二项" in out
    assert "附注五" in out and "(x)" not in out
    assert "TB(1121)" in out and "`" not in out


def test_html_passthrough():
    html = "<p>期末余额 <strong>1000</strong></p>"
    assert sanitize_note_narrative(html) == html
    # 前导空白后是 HTML 也原样
    assert sanitize_note_narrative("  <p>x</p>") == "  <p>x</p>"


def test_plain_text_unchanged():
    plain = "本公司货币资金期末余额为 100 万元。"
    assert sanitize_note_narrative(plain) == plain


@settings(max_examples=30)
@given(st.text(min_size=0, max_size=200))
def test_idempotent_and_no_markdown(text: str):
    once = sanitize_note_narrative(text)
    twice = sanitize_note_narrative(once)
    # Property 1: 幂等
    assert once == twice
    # 非 HTML 输出不含标题标记/裸加粗（HTML 原样分支除外）
    if once and not once.lstrip().startswith("<"):
        assert not _HEADING.search(once)
        assert not _BOLD.search(once)
