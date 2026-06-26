"""Property 8: 一致性校验输出 schema 不变式

∀ 输入到一致性校验引擎的章节内容集合，输出列表中的每一项都满足:
  - rule_id: 非空字符串
  - severity: "error" | "warning" | "info" 之一
  - affected_chapters: 非空列表，每个元素为合法章节 ID
  - description: 非空字符串

# Feature: a17-summary-enhancement, Property 8: 一致性校验输出 schema 不变式

**Validates: Requirements 3.3**
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
VALID_CHAPTER_ID_PATTERN = r"^A17-1-ch\d{2}$"

VALID_SEVERITIES = {"error", "warning", "info"}

# 生成随机章节内容（含可能的触发关键词以确保有输出可验证）
trigger_keywords = [
    "重大不确定性", "持续经营存疑", "重大疑虑",
    "标准无保留", "无保留意见",
    "舞弊", "fraud", "虚假",
    "保留", "否定", "无法表示",
    "未解决", "遗留", "未应对", "未消除",
    "正常审计", "无异常", "符合预期",
]

chapter_content = st.one_of(
    st.none(),
    st.text(min_size=0, max_size=50),
    st.sampled_from(trigger_keywords).map(lambda kw: f"内容包含{kw}的描述"),
)

business_category_st = st.one_of(
    st.none(),
    st.sampled_from(["上市公司", "非上市公司", "国有企业", "民营企业"]),
)


@st.composite
def chapter_dict_strategy(draw):
    """生成 16 章内容字典，随机填充内容。"""
    chapters = {}
    for ch_id in CHAPTER_IDS:
        chapters[ch_id] = draw(chapter_content)
    return chapters


# ─── Property 8: Schema invariant ────────────────────────────────────────


@settings(max_examples=100)
@given(
    chapters=chapter_dict_strategy(),
    category=business_category_st,
)
def test_consistency_output_schema_invariant(chapters, category):
    """一致性校验输出的每一项都满足 schema 不变式。"""
    results = check_consistency(chapters, business_category=category)

    # results 必须是 list
    assert isinstance(results, list)

    for result in results:
        # rule_id: 非空字符串
        assert isinstance(result.rule_id, str)
        assert len(result.rule_id) > 0

        # severity: 限定枚举
        assert result.severity in VALID_SEVERITIES, (
            f"Invalid severity: {result.severity}"
        )

        # affected_chapters: 非空列表
        assert isinstance(result.affected_chapters, list)
        assert len(result.affected_chapters) > 0

        # affected_chapters 中的每个元素都是合法章节 ID
        import re
        for ch_id in result.affected_chapters:
            assert isinstance(ch_id, str)
            assert re.match(VALID_CHAPTER_ID_PATTERN, ch_id), (
                f"Invalid chapter ID: {ch_id}"
            )

        # description: 非空字符串
        assert isinstance(result.description, str)
        assert len(result.description) > 0


@settings(max_examples=100)
@given(
    chapters=chapter_dict_strategy(),
    category=business_category_st,
)
def test_consistency_results_only_known_rule_ids(chapters, category):
    """输出的 rule_id 只能是已知的 4 个规则之一。"""
    known_rule_ids = {
        "gc_vs_opinion",
        "kam_required_listed",
        "fraud_vs_opinion",
        "risk_vs_opinion",
    }

    results = check_consistency(chapters, business_category=category)

    for result in results:
        assert result.rule_id in known_rule_ids, (
            f"Unknown rule_id: {result.rule_id}"
        )
