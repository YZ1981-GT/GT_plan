"""知识库文档词法检索 —— 纯函数单测 + PBT（spec knowledge-base-retrieval-and-authz-closure P7）。

覆盖：检索词规则（Req 2.2）、LIKE 转义、打分单调性（Req 2.5）、片段窗口（Req 2.4）、
jieba 缺失时的分词降级（Req 1.4）。SQL 与判定面的行为由 ``test_knowledge_doc_search_pg`` 在真库覆盖。
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services import _zh_tokenize as zt
from app.services.knowledge_doc_search import (
    SNIPPET_CHARS,
    best_window,
    escape_like,
    score_document,
)


# ── 检索词 ──────────────────────────────────────────────────────────────────


def test_escape_like_escapes_all_wildcards():
    assert escape_like("100%") == "100\\%"
    assert escape_like("a_b") == "a\\_b"
    assert escape_like("c:\\x") == "c:\\\\x"
    assert escape_like("普通文本") == "普通文本"


def test_query_terms_drops_punctuation_and_stopwords():
    assert zt.query_terms("") == []
    assert zt.query_terms("   ") == []
    assert zt.query_terms("%") == []
    assert zt.query_terms("，。！") == []
    terms = zt.query_terms("关于 应收账款 以及 坏账准备")
    assert "关于" not in terms and "以及" not in terms
    assert terms, terms


def test_query_terms_keeps_single_char_query_but_drops_singles_among_words():
    assert zt.query_terms("税") == ["税"]
    terms = zt.query_terms("应收账款 的 审计")
    assert all(len(t) > 1 for t in terms)


def test_query_terms_cap_keeps_longest_in_original_order():
    words = [f"词{i:02d}" + "长" * (i % 4) for i in range(20)]
    terms = zt.query_terms(" ".join(words), max_terms=5)
    assert len(terms) <= 5
    # 输出保持原始相对顺序（确定性）
    positions = [" ".join(words).find(t) for t in terms]
    assert positions == sorted(positions)
    assert zt.query_terms(" ".join(words), max_terms=5) == terms


def test_fallback_tokenizer_without_jieba(monkeypatch):
    monkeypatch.setattr(zt, "JIEBA_AVAILABLE", False)
    assert zt.zh_tokenize("应收账款 AR-2024") == ["应收", "收账", "账款", "ar-2024"]
    assert zt.zh_tokenize("税") == ["税"]
    assert zt.query_terms("坏账准备") == ["坏账", "账准", "准备"]


# ── 打分 ────────────────────────────────────────────────────────────────────


def test_score_coverage_dominates_term_frequency():
    terms = ["收入", "确认", "五步法"]
    full = score_document(terms, "准则.md", "收入 确认 五步法")[0]
    partial_high_tf = score_document(terms, "准则.md", "收入" * 50)[0]
    assert full > partial_high_tf


def test_score_name_hit_and_bonus_and_bounds():
    terms = ["坏账"]
    plain = score_document(terms, "a.md", "坏账")[0]
    named = score_document(terms, "坏账政策.md", "坏账")[0]
    boosted = score_document(terms, "a.md", "坏账", in_category=True)[0]
    assert named > plain and boosted > plain
    assert score_document(terms, "坏账.md", "坏账" * 100, in_category=True, boost_terms=["坏账"] * 9)[0] <= 1.0
    assert score_document([], "a.md", "x") == (0.0, ())
    assert score_document([], "a.md", "x", in_category=True)[0] > 0
    assert score_document(terms, "a.md", "无关")[0] == 0.0


def test_score_counts_tags_toward_coverage():
    score, matched = score_document(["函证"], "a.md", "正文无关", tags=["函证", "银行"])
    assert matched == ("函证",) and score > 0


# ── 片段 ────────────────────────────────────────────────────────────────────


def test_best_window_short_content_returned_whole():
    assert best_window("短文本", ["短"]) == ("短文本", 0)
    assert best_window("", ["x"]) == ("", 0)


def test_best_window_prefers_window_with_most_distinct_terms():
    content = "甲" + "填充" * 400 + "甲乙丙" + "填充" * 400
    snippet, chunk = best_window(content, ["甲", "乙", "丙"])
    assert "甲乙丙" in snippet and len(snippet) == SNIPPET_CHARS and chunk >= 1


def test_best_window_without_match_takes_head():
    content = "开头" + "x" * 1000
    assert best_window(content, ["不存在"]) == (content[:SNIPPET_CHARS], 0)


@settings(max_examples=5, deadline=None)
@given(
    prefix=st.integers(min_value=0, max_value=3000),
    suffix=st.integers(min_value=0, max_value=3000),
    term=st.text(alphabet="应收账款坏账ABC", min_size=1, max_size=6),
)
def test_pbt_snippet_bounded_and_contains_term(prefix, suffix, term):
    content = "填" * prefix + term + "充" * suffix
    snippet, chunk = best_window(content, [term])
    assert len(snippet) <= SNIPPET_CHARS
    assert term in snippet
    assert chunk == (content.find(snippet) // SNIPPET_CHARS if len(content) > SNIPPET_CHARS else 0)
