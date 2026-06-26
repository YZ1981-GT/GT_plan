"""Property 7: 一致性校验规则引擎正确触发

∀ 16 章内容集合 chapters, ∀ business_category:
  (a) ch10 匹配"重大不确定性" AND ch14 匹配"标准无保留" → WARNING gc_vs_opinion
  (b) ch12 为空 AND business_category == "上市公司" → ERROR kam_required_listed
  (c) ch15 匹配舞弊指标 AND ch14 未提及保留/否定/无法表示 → WARNING fraud_vs_opinion
  (d) ch06 提及未解决风险 AND ch14 为无保留 → WARNING risk_vs_opinion
  当以上条件均不满足时，结果为空。

# Feature: a17-summary-enhancement, Property 7: 一致性校验规则引擎正确触发

**Validates: Requirements 3.2, 3.3, 3.6**
"""

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.a17_consistency_checker import check_consistency


# ─── Strategies ───────────────────────────────────────────────────────────

CHAPTER_IDS = [f"A17-1-ch{i:02d}" for i in range(1, 17)]

# 内容生成器：生成有意义的中文审计文本或空字符串
safe_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=0,
    max_size=200,
)

# 特定关键词策略
gc_trigger_phrases = st.sampled_from(["重大不确定性", "持续经营存疑", "重大疑虑"])
opinion_unqualified = st.sampled_from(["标准无保留", "无保留意见", "出具标准无保留审计意见"])
fraud_trigger = st.sampled_from(["舞弊", "fraud", "虚假", "发现舞弊线索"])
opinion_qualified = st.sampled_from(["保留意见", "否定意见", "无法表示意见"])
risk_trigger = st.sampled_from(["未解决", "遗留风险", "未应对", "未消除"])
business_categories = st.sampled_from(["上市公司", "非上市公司", "国有企业", "民营企业"])


def make_chapters(**overrides) -> dict[str, str | None]:
    """创建 16 章空字典，可按需覆盖特定章节内容。"""
    chapters = {ch_id: None for ch_id in CHAPTER_IDS}
    chapters.update(overrides)
    return chapters


# ─── Property 7a: gc_vs_opinion ──────────────────────────────────────────


@settings(max_examples=100)
@given(
    gc_phrase=gc_trigger_phrases,
    opinion_phrase=opinion_unqualified,
    filler=safe_text,
)
def test_gc_vs_opinion_triggers(gc_phrase, opinion_phrase, filler):
    """ch10 含持续经营存疑 + ch14 含标准无保留 → WARNING gc_vs_opinion"""
    chapters = make_chapters(
        **{
            "A17-1-ch10": f"经评估，存在{gc_phrase}，管理层{filler}",
            "A17-1-ch14": f"我们出具{opinion_phrase}的审计报告{filler}",
        }
    )
    results = check_consistency(chapters, business_category="非上市公司")
    gc_results = [r for r in results if r.rule_id == "gc_vs_opinion"]
    assert len(gc_results) == 1
    assert gc_results[0].severity == "warning"
    assert "A17-1-ch10" in gc_results[0].affected_chapters
    assert "A17-1-ch14" in gc_results[0].affected_chapters


# ─── Property 7b: kam_required_listed ────────────────────────────────────


@settings(max_examples=100)
@given(filler=safe_text)
def test_kam_required_when_listed_company(filler):
    """ch12 为空 + 上市公司 → ERROR kam_required_listed"""
    # ch12 为空（None 或仅空白/HTML空标签）
    chapters = make_chapters(**{"A17-1-ch12": None})
    results = check_consistency(chapters, business_category="上市公司")
    kam_results = [r for r in results if r.rule_id == "kam_required_listed"]
    assert len(kam_results) == 1
    assert kam_results[0].severity == "error"
    assert "A17-1-ch12" in kam_results[0].affected_chapters


@settings(max_examples=100)
@given(category=st.sampled_from(["非上市公司", "国有企业", "民营企业"]))
def test_kam_not_triggered_for_non_listed(category):
    """ch12 为空但非上市公司 → 不触发 kam_required_listed"""
    chapters = make_chapters(**{"A17-1-ch12": None})
    results = check_consistency(chapters, business_category=category)
    kam_results = [r for r in results if r.rule_id == "kam_required_listed"]
    assert len(kam_results) == 0


@settings(max_examples=100)
@given(filler=safe_text)
def test_kam_not_triggered_when_category_null(filler):
    """business_category 为 None → 跳过 kam_required_listed"""
    chapters = make_chapters(**{"A17-1-ch12": None})
    results = check_consistency(chapters, business_category=None)
    kam_results = [r for r in results if r.rule_id == "kam_required_listed"]
    assert len(kam_results) == 0


# ─── Property 7c: fraud_vs_opinion ───────────────────────────────────────


@settings(max_examples=100)
@given(
    fraud_phrase=fraud_trigger,
    filler=safe_text,
)
def test_fraud_vs_opinion_triggers(fraud_phrase, filler):
    """ch15 含舞弊指标 + ch14 未提及保留/否定/无法表示 → WARNING"""
    chapters = make_chapters(
        **{
            "A17-1-ch15": f"审计中发现{fraud_phrase}相关线索{filler}",
            "A17-1-ch14": f"审计结论：我们认为财务报表公允{filler}",
        }
    )
    results = check_consistency(chapters, business_category="非上市公司")
    fraud_results = [r for r in results if r.rule_id == "fraud_vs_opinion"]
    assert len(fraud_results) == 1
    assert fraud_results[0].severity == "warning"


@settings(max_examples=100)
@given(
    fraud_phrase=fraud_trigger,
    qualified_phrase=opinion_qualified,
    filler=safe_text,
)
def test_fraud_vs_opinion_not_triggered_when_qualified(fraud_phrase, qualified_phrase, filler):
    """ch15 含舞弊指标 + ch14 已提及保留/否定 → 不触发"""
    chapters = make_chapters(
        **{
            "A17-1-ch15": f"发现{fraud_phrase}线索",
            "A17-1-ch14": f"出具{qualified_phrase}{filler}",
        }
    )
    results = check_consistency(chapters, business_category="非上市公司")
    fraud_results = [r for r in results if r.rule_id == "fraud_vs_opinion"]
    assert len(fraud_results) == 0


# ─── Property 7d: risk_vs_opinion ────────────────────────────────────────


@settings(max_examples=100)
@given(
    risk_phrase=risk_trigger,
    opinion_phrase=opinion_unqualified,
    filler=safe_text,
)
def test_risk_vs_opinion_triggers(risk_phrase, opinion_phrase, filler):
    """ch06 含未应对风险 + ch14 含标准无保留 → WARNING"""
    chapters = make_chapters(
        **{
            "A17-1-ch06": f"存在{risk_phrase}的重大错报风险{filler}",
            "A17-1-ch14": f"出具{opinion_phrase}的审计报告{filler}",
        }
    )
    results = check_consistency(chapters, business_category="非上市公司")
    risk_results = [r for r in results if r.rule_id == "risk_vs_opinion"]
    assert len(risk_results) == 1
    assert risk_results[0].severity == "warning"


# ─── No false positives ──────────────────────────────────────────────────


@settings(max_examples=100)
@given(
    ch06=safe_text,
    ch10=safe_text,
    ch12_content=st.text(min_size=5, max_size=50),
    ch14=safe_text,
    ch15=safe_text,
    category=st.one_of(business_categories, st.none()),
)
def test_no_false_positives_when_no_triggers(ch06, ch10, ch12_content, ch14, ch15, category):
    """无触发条件时结果为空。

    构造内容不包含任何触发关键词。
    """
    # 确保生成的内容不包含任何触发关键词
    trigger_words = [
        "重大不确定性", "持续经营", "存疑", "重大疑虑",
        "标准无保留", "无保留意见",
        "舞弊", "fraud", "虚假",
        "保留", "否定", "无法表示",
        "未解决", "遗留", "未应对", "未消除",
    ]
    all_content = ch06 + ch10 + ch14 + ch15
    assume(not any(kw in all_content for kw in trigger_words))
    # ch12 非空以避免 kam_required_listed
    assume(len(ch12_content.strip()) > 0)

    chapters = make_chapters(
        **{
            "A17-1-ch06": ch06,
            "A17-1-ch10": ch10,
            "A17-1-ch12": ch12_content,
            "A17-1-ch14": ch14,
            "A17-1-ch15": ch15,
        }
    )
    results = check_consistency(chapters, business_category=category)
    assert len(results) == 0, f"Unexpected results: {[r.rule_id for r in results]}"
