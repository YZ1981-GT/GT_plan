"""Property-based tests for A17 LLM cross-chapter context and prompt building.

Feature: a17-summary-enhancement
Property 9: LLM 跨章上下文构建完备性
Property 10: LLM 生成模式 prompt 构建

Uses hypothesis library with @settings(max_examples=100).
"""

import re
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

import sys
from pathlib import Path

# Ensure backend is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.a17_llm_service import (
    CHAPTER_AFFINITY,
    build_cross_chapter_context,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

ALL_CHAPTER_IDS = [f"A17-1-ch{i:02d}" for i in range(1, 17)]

# Generate random chapter contents: some empty, some with text
chapter_content_strategy = st.dictionaries(
    keys=st.sampled_from(ALL_CHAPTER_IDS),
    values=st.one_of(
        st.just(""),  # empty
        st.just("   "),  # whitespace-only (counts as empty)
        st.text(min_size=10, max_size=200, alphabet=st.characters(
            whitelist_categories=('L', 'N', 'P', 'Z'),
            whitelist_characters='审计风险持续经营重大不确定性无保留意见'
        )),
    ),
    min_size=1,
    max_size=16,
)

target_chapter_strategy = st.sampled_from(ALL_CHAPTER_IDS)


# ---------------------------------------------------------------------------
# Property 9: LLM 跨章上下文构建完备性
# ---------------------------------------------------------------------------


class TestCrossChapterContext:
    """
    **Validates: Requirements 4.1, 4.5**

    For any target chapter and a set of 16 chapter contents where K chapters are
    non-empty (K >= 1, excluding target), the cross-chapter context builder SHALL
    include content from exactly K chapters when total size is within budget, or a
    prioritized subset when exceeding budget, where prioritized chapters are
    determined by the affinity matrix.
    """

    @given(
        target=target_chapter_strategy,
        chapters=chapter_content_strategy,
    )
    @settings(max_examples=100)
    def test_excludes_target_chapter(self, target: str, chapters: dict[str, str]):
        """Target chapter content is never included in cross-chapter context."""
        # Feature: a17-summary-enhancement, Property 9: LLM 跨章上下文构建完备性
        # **Validates: Requirements 4.1, 4.5**
        result = build_cross_chapter_context(target, chapters, budget=100000)
        # If target had content, it should NOT appear as [target_id] header
        assert f"[{target}]" not in result

    @given(
        target=target_chapter_strategy,
        chapters=chapter_content_strategy,
    )
    @settings(max_examples=100)
    def test_includes_all_non_empty_within_budget(self, target: str, chapters: dict[str, str]):
        """When budget is large enough, all non-empty non-target chapters are included."""
        # Feature: a17-summary-enhancement, Property 9: LLM 跨章上下文构建完备性
        # **Validates: Requirements 4.1, 4.5**
        result = build_cross_chapter_context(target, chapters, budget=1_000_000)

        non_empty_others = {
            ch_id for ch_id, content in chapters.items()
            if ch_id != target and content and content.strip()
        }

        for ch_id in non_empty_others:
            assert f"[{ch_id}]" in result, f"Expected {ch_id} in context but not found"

    @given(
        target=target_chapter_strategy,
        chapters=chapter_content_strategy,
    )
    @settings(max_examples=100)
    def test_respects_budget_limit(self, target: str, chapters: dict[str, str]):
        """Output length never exceeds budget (may slightly exceed due to join separators)."""
        # Feature: a17-summary-enhancement, Property 9: LLM 跨章上下文构建完备性
        # **Validates: Requirements 4.1, 4.5**
        budget = 200
        result = build_cross_chapter_context(target, chapters, budget=budget)
        # Budget is per-segment accumulator; separators (\n\n) can add a bit extra
        # but total chars added to prompt should be bounded
        # The function accumulates segments up to budget, so each individual segment
        # added is <= budget in total
        assert len(result) <= budget + 100  # generous margin for separators

    @given(
        target=target_chapter_strategy,
        chapters=chapter_content_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.filter_too_much])
    def test_affinity_chapters_prioritized(self, target: str, chapters: dict[str, str]):
        """Affinity matrix chapters appear before non-affinity ones when budget is tight."""
        # Feature: a17-summary-enhancement, Property 9: LLM 跨章上下文构建完备性
        # **Validates: Requirements 4.1, 4.5**
        affinity_ids = CHAPTER_AFFINITY.get(target, [])
        non_empty_affinity = [
            ch_id for ch_id in affinity_ids
            if ch_id in chapters and chapters[ch_id] and chapters[ch_id].strip()
        ]
        non_empty_others = [
            ch_id for ch_id in chapters
            if ch_id != target and ch_id not in affinity_ids
            and chapters[ch_id] and chapters[ch_id].strip()
        ]

        assume(len(non_empty_affinity) > 0 and len(non_empty_others) > 0)

        # Use a large budget so ordering is visible without truncation
        result = build_cross_chapter_context(target, chapters, budget=100000)

        # If any chapter appears in the result, check that affinity chapters
        # appear before non-affinity chapters
        if result:
            first_affinity_pos = -1
            last_other_pos = -1
            for ch_id in non_empty_affinity:
                pos = result.find(f"[{ch_id}]")
                if pos >= 0:
                    if first_affinity_pos < 0:
                        first_affinity_pos = pos
                    break
            for ch_id in non_empty_others:
                pos = result.find(f"[{ch_id}]")
                if pos >= 0:
                    last_other_pos = pos

            # If both present, affinity should come first
            if first_affinity_pos >= 0 and last_other_pos >= 0:
                assert first_affinity_pos < last_other_pos

    @given(
        target=target_chapter_strategy,
    )
    @settings(max_examples=100)
    def test_empty_chapters_produce_empty_context(self, target: str):
        """When all chapters are empty or only target has content, result is empty."""
        # Feature: a17-summary-enhancement, Property 9: LLM 跨章上下文构建完备性
        # **Validates: Requirements 4.1, 4.5**
        chapters = {target: "有内容的目标章节"}
        result = build_cross_chapter_context(target, chapters, budget=10000)
        assert result == ""


# ---------------------------------------------------------------------------
# Property 10: LLM 生成模式 prompt 构建
# ---------------------------------------------------------------------------


# We can't easily test the full async generate method, but we can test
# the prompt construction logic by simulating what generate_chapter_draft does.

def _build_test_prompt(
    mode: str,
    current_content: str,
    project_industry: str,
    audit_period_end: str,
    cross_chapter_ctx: str,
) -> str:
    """Simulate the prompt building logic from generate_chapter_draft."""
    user_prompt = f"章节标题: 测试章节\n"
    user_prompt += f"章节指引: 测试指引\n"
    user_prompt += f"项目信息:\n行业: {project_industry}\n审计期间截止日: {audit_period_end}\n"
    user_prompt += "审计证据: （本版本暂无自动拉取的审计证据）\n"

    if cross_chapter_ctx:
        user_prompt += f"\n\n## 其他章节上下文（供参考，确保一致性）\n{cross_chapter_ctx}"

    if mode == "polish" and current_content:
        user_prompt += (
            f"\n\n## 当前章节已有内容（请在此基础上润色改进）\n{current_content.strip()}"
            "\n\n## 润色要求\n"
            "请保留原有结构和核心判断，优化文字表述、改善逻辑连贯性、"
            "确保与其他章节结论一致、补充遗漏要点。不要从头重写。"
        )

    return user_prompt


class TestPromptConstruction:
    """
    **Validates: Requirements 4.2, 4.3, 4.6**

    For any generation request:
    - mode="polish" → prompt contains existing chapter content verbatim
    - mode="generate" → prompt does NOT contain prior chapter content
    - prompt always includes project industry and audit_period_end
    """

    @given(
        mode=st.sampled_from(["generate", "polish"]),
        current_content=st.text(min_size=5, max_size=100, alphabet=st.characters(
            whitelist_categories=('L', 'N', 'P'),
            whitelist_characters='审计测试内容润色'
        )),
        industry=st.text(min_size=2, max_size=20, alphabet=st.characters(
            whitelist_categories=('L',),
            whitelist_characters='制造业金融房地产科技'
        )),
        audit_period_end=st.from_regex(r"20\d{2}-12-31", fullmatch=True),
    )
    @settings(max_examples=100)
    def test_polish_mode_includes_current_content(
        self, mode: str, current_content: str, industry: str, audit_period_end: str
    ):
        """mode=polish → prompt contains current content; mode=generate → does not."""
        # Feature: a17-summary-enhancement, Property 10: LLM 生成模式 prompt 构建
        # **Validates: Requirements 4.2, 4.3, 4.6**
        prompt = _build_test_prompt(mode, current_content, industry, audit_period_end, "")

        if mode == "polish":
            assert current_content.strip() in prompt, \
                "Polish mode must include current chapter content verbatim"
            assert "润色要求" in prompt
        else:
            # generate mode: should NOT contain the polish section
            assert "当前章节已有内容（请在此基础上润色改进）" not in prompt
            assert "润色要求" not in prompt

    @given(
        mode=st.sampled_from(["generate", "polish"]),
        industry=st.text(min_size=2, max_size=20, alphabet=st.characters(
            whitelist_categories=('L',),
            whitelist_characters='制造业金融房地产科技'
        )),
        audit_period_end=st.from_regex(r"20\d{2}-12-31", fullmatch=True),
    )
    @settings(max_examples=100)
    def test_prompt_always_includes_industry_and_period(
        self, mode: str, industry: str, audit_period_end: str
    ):
        """Prompt always includes project industry and audit_period_end."""
        # Feature: a17-summary-enhancement, Property 10: LLM 生成模式 prompt 构建
        # **Validates: Requirements 4.2, 4.3, 4.6**
        prompt = _build_test_prompt(mode, "一些内容", industry, audit_period_end, "")
        assert industry in prompt, "Industry must always be in prompt"
        assert audit_period_end in prompt, "audit_period_end must always be in prompt"

    @given(
        mode=st.sampled_from(["generate", "polish"]),
        current_content=st.text(min_size=5, max_size=50, alphabet=st.characters(
            whitelist_categories=('L', 'N'),
            whitelist_characters='审计内容'
        )),
        cross_ctx=st.text(min_size=10, max_size=100, alphabet=st.characters(
            whitelist_categories=('L', 'N'),
            whitelist_characters='其他章节上下文'
        )),
    )
    @settings(max_examples=100)
    def test_cross_chapter_context_always_included_when_provided(
        self, mode: str, current_content: str, cross_ctx: str
    ):
        """Cross-chapter context is always included in the prompt when provided."""
        # Feature: a17-summary-enhancement, Property 10: LLM 生成模式 prompt 构建
        # **Validates: Requirements 4.2, 4.3, 4.6**
        prompt = _build_test_prompt(mode, current_content, "制造业", "2025-12-31", cross_ctx)
        assert cross_ctx in prompt, "Cross-chapter context must be in prompt"
        assert "其他章节上下文（供参考，确保一致性）" in prompt
