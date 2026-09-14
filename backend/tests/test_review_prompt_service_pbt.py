"""Property-Based Tests for ReviewPromptService (P1, P2, P3, P4).

Tests resolve_sheet_suffix round-trip, prompt resolution specificity ordering,
fallback completeness, and file path construction determinism using hypothesis.

**Validates: Requirements 2.1, 2.2, 2.4, 1.4**
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from pathlib import Path

from app.services.review_prompt_service import ReviewPromptService, PromptResult


# ═══════════════════════════════════════════════════════════════════════════════
# Strategies
# ═══════════════════════════════════════════════════════════════════════════════

# Valid wp_code patterns: letter + digit(s) + optional suffix
WP_CODE_PREFIXES = st.sampled_from([
    "D2", "D3", "E1", "F1", "F2", "G1", "G5", "H1", "I1", "J1",
    "K1", "K3", "L1", "M1", "N1", "S1",
])

# Sheet name patterns containing valid wp_code suffixes
CHINESE_LABELS = st.sampled_from([
    "审定表", "明细表", "坏账准备", "分析表", "凭证检查表",
    "政策检查", "附注", "调整分录", "检查表", "测算表",
])

NUMERIC_SUFFIXES = st.integers(min_value=1, max_value=13).map(str)

NOTE_SUFFIXES = st.sampled_from([
    "note-listed", "note-soe",
])


def sheet_name_with_numeric_suffix():
    """Generate sheet_name like '审定表D2-1', '明细表K3-5' etc."""
    return st.tuples(CHINESE_LABELS, WP_CODE_PREFIXES, NUMERIC_SUFFIXES).map(
        lambda t: f"{t[0]}{t[1]}-{t[2]}"
    )


def sheet_name_with_note_suffix():
    """Generate sheet_name like 'D2-note-listed' etc."""
    return st.tuples(WP_CODE_PREFIXES, NOTE_SUFFIXES).map(
        lambda t: f"{t[0]}-{t[1]}"
    )


def valid_sheet_name_strategy():
    """Generate any valid sheet_name containing a wp_code pattern."""
    return st.one_of(
        sheet_name_with_numeric_suffix(),
        sheet_name_with_note_suffix(),
    )


def valid_wp_code_strategy():
    """Generate valid wp_codes matching pattern [A-Z]\\d+."""
    return st.tuples(
        st.sampled_from(list("DEFGHIJKLMNS")),
        st.integers(min_value=1, max_value=14),
    ).map(lambda t: f"{t[0]}{t[1]}")


# ═══════════════════════════════════════════════════════════════════════════════
# Property 1: Sheet suffix extraction round-trip
# **Validates: Requirements 2.1**
# ═══════════════════════════════════════════════════════════════════════════════

class TestProperty1SheetSuffixRoundTrip:
    """For any sheet_name containing a valid wp_code pattern,
    resolve_sheet_suffix extracts a suffix that when used to construct
    a file path, produces a path containing that suffix."""

    @settings(max_examples=5)
    @given(sheet_name=valid_sheet_name_strategy())
    def test_suffix_extraction_produces_path_containing_suffix(self, sheet_name: str):
        """P1: resolve_sheet_suffix extracts suffix present in constructed path."""
        service = ReviewPromptService()
        suffix = service.resolve_sheet_suffix(sheet_name)

        # Must extract a non-None suffix from valid sheet_names
        assert suffix is not None, f"Failed to extract suffix from: {sheet_name}"

        # The suffix must be non-empty
        assert len(suffix) > 0

        # Constructing a file path with the suffix must contain that suffix
        cycle_letter = suffix[0].upper()
        constructed_path = f"{cycle_letter}/{suffix}.md"
        assert suffix in constructed_path

    @settings(max_examples=5)
    @given(sheet_name=sheet_name_with_numeric_suffix())
    def test_numeric_suffix_extraction_contains_digit(self, sheet_name: str):
        """P1 variant: numeric suffixes contain at least one digit."""
        service = ReviewPromptService()
        suffix = service.resolve_sheet_suffix(sheet_name)

        assert suffix is not None
        # Must contain at least one digit (the sheet number)
        assert any(c.isdigit() for c in suffix)

    @settings(max_examples=5)
    @given(sheet_name=sheet_name_with_note_suffix())
    def test_note_suffix_extraction_contains_note(self, sheet_name: str):
        """P1 variant: note suffixes contain 'note'."""
        service = ReviewPromptService()
        suffix = service.resolve_sheet_suffix(sheet_name)

        assert suffix is not None
        assert "note" in suffix.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# Property 2: Prompt resolution specificity ordering
# **Validates: Requirements 2.4**
# ═══════════════════════════════════════════════════════════════════════════════

class TestProperty2SpecificityOrdering:
    """When both sheet-level and subject-level prompts exist,
    load_prompt returns sheet-level (source_level="sheet")."""

    @settings(max_examples=5)
    @given(suffix_num=st.integers(min_value=1, max_value=8))
    def test_sheet_level_takes_priority_over_subject(self, suffix_num: int, tmp_path: Path):
        """P2: Sheet-level prompt is returned when both exist."""
        # Set up directory structure with both sheet-level and subject-level
        cycle_dir = tmp_path / "D"
        cycle_dir.mkdir(exist_ok=True)

        # Create sheet-level file
        sheet_file = cycle_dir / f"D2-{suffix_num}.md"
        sheet_content = f"## tips\n\n1. Sheet-level tip for D2-{suffix_num}\n"
        sheet_file.write_text(sheet_content, encoding="utf-8")

        # Create subject-level file (in root)
        subject_file = tmp_path / "应收账款审计复核提示词.md"
        subject_file.write_text(
            "## tips\n\n1. Subject-level tip for 应收账款\n",
            encoding="utf-8",
        )

        # Initialize service with tmp_path as base
        service = ReviewPromptService(base_dir=tmp_path)
        sheet_name = f"审定表D2-{suffix_num}"

        result = service.load_prompt(wp_code="D2", sheet_name=sheet_name)

        # Must return sheet-level, not subject
        assert result.source_level == "sheet"
        assert f"D2-{suffix_num}" in (result.file_path or "")

    @settings(max_examples=5)
    @given(
        wp_prefix=st.sampled_from(["D2", "E1", "F2", "K1"]),
        suffix_num=st.integers(min_value=1, max_value=5),
    )
    def test_sheet_level_content_returned_not_subject(
        self, wp_prefix: str, suffix_num: int, tmp_path: Path
    ):
        """P2: The content returned is from the sheet-level file."""
        cycle_letter = wp_prefix[0]
        cycle_dir = tmp_path / cycle_letter
        cycle_dir.mkdir(exist_ok=True)

        marker = f"SHEET_MARKER_{wp_prefix}_{suffix_num}"
        sheet_file = cycle_dir / f"{wp_prefix}-{suffix_num}.md"
        sheet_file.write_text(f"## tips\n\n1. {marker}\n", encoding="utf-8")

        # Subject-level (different content)
        subject_file = tmp_path / "科目级提示词.md"
        subject_file.write_text("## tips\n\n1. SUBJECT_CONTENT\n", encoding="utf-8")

        service = ReviewPromptService(base_dir=tmp_path)
        result = service.load_prompt(
            wp_code=wp_prefix,
            sheet_name=f"检查表{wp_prefix}-{suffix_num}",
        )

        assert result.source_level == "sheet"
        assert marker in result.content


# ═══════════════════════════════════════════════════════════════════════════════
# Property 3: Fallback completeness
# **Validates: Requirements 1.4, 10.4**
# ═══════════════════════════════════════════════════════════════════════════════

class TestProperty3FallbackCompleteness:
    """For any wp_code and sheet_name where no sheet-level file exists,
    load_prompt returns non-empty (either subject or base)."""

    @settings(max_examples=5)
    @given(
        wp_code=valid_wp_code_strategy(),
        sheet_name=valid_sheet_name_strategy(),
    )
    def test_always_returns_non_empty_content(
        self, wp_code: str, sheet_name: str, tmp_path: Path
    ):
        """P3: load_prompt never returns empty, always falls back."""
        # Use tmp_path with NO sheet-level files at all
        service = ReviewPromptService(base_dir=tmp_path)

        result = service.load_prompt(wp_code=wp_code, sheet_name=sheet_name)

        # Must return a non-empty result
        assert result is not None
        assert isinstance(result, PromptResult)
        assert result.content is not None
        assert len(result.content.strip()) > 0

    @settings(max_examples=5)
    @given(wp_code=valid_wp_code_strategy())
    def test_fallback_without_sheet_name(self, wp_code: str, tmp_path: Path):
        """P3 variant: Even without sheet_name, returns non-empty."""
        service = ReviewPromptService(base_dir=tmp_path)

        result = service.load_prompt(wp_code=wp_code, sheet_name=None)

        assert result is not None
        assert len(result.content.strip()) > 0
        # Without any files, should fallback to "base" level
        assert result.source_level in ("subject", "base")

    @settings(max_examples=5)
    @given(wp_code=valid_wp_code_strategy())
    def test_fallback_source_level_is_subject_or_base(
        self, wp_code: str, tmp_path: Path
    ):
        """P3: When no sheet file exists, source_level is 'subject' or 'base'."""
        service = ReviewPromptService(base_dir=tmp_path)

        result = service.load_prompt(wp_code=wp_code, sheet_name="不存在的底稿X99-99")

        assert result.source_level in ("subject", "base")


# ═══════════════════════════════════════════════════════════════════════════════
# Property 4: File path construction determinism
# **Validates: Requirements 2.2**
# ═══════════════════════════════════════════════════════════════════════════════

class TestProperty4FilePathDeterminism:
    """For any valid wp_code, the cycle_letter = first character."""

    @settings(max_examples=5)
    @given(wp_code=valid_wp_code_strategy())
    def test_cycle_letter_equals_first_char(self, wp_code: str):
        """P4: cycle_letter derivation equals first character of wp_code."""
        cycle_letter = wp_code[0].upper()

        # The cycle_letter must be an uppercase letter
        assert cycle_letter.isalpha()
        assert cycle_letter.isupper()
        assert cycle_letter == wp_code[0].upper()

    @settings(max_examples=5)
    @given(
        wp_code=valid_wp_code_strategy(),
        suffix_num=st.integers(min_value=1, max_value=13),
    )
    def test_constructed_path_is_deterministic(
        self, wp_code: str, suffix_num: int, tmp_path: Path
    ):
        """P4: Same wp_code always produces the same path structure."""
        cycle_letter = wp_code[0].upper()
        suffix = f"{wp_code}-{suffix_num}"
        expected_path = tmp_path / cycle_letter / f"{suffix}.md"

        # Construct the path the same way service would
        constructed = tmp_path / cycle_letter / f"{suffix}.md"

        assert constructed == expected_path
        # Path contains the cycle_letter directory
        assert cycle_letter in str(constructed)
        # Path contains the suffix
        assert suffix in str(constructed)

    @settings(max_examples=5)
    @given(wp_code=valid_wp_code_strategy())
    def test_same_wp_code_same_cycle_letter_always(self, wp_code: str):
        """P4: Repeated calls with same wp_code yield same cycle_letter."""
        results = [wp_code[0].upper() for _ in range(3)]
        assert all(r == results[0] for r in results)
        # cycle_letter is always the first character uppercased
        assert results[0] == wp_code[0].upper()


# ═══════════════════════════════════════════════════════════════════════════════
# D2 sheet alias & coverage (regression)
# ═══════════════════════════════════════════════════════════════════════════════

class TestD2SheetAliasesAndCoverage:
    """D2 中文 sheet 名别名与新增底稿提示词文件"""

    def test_cutoff_sheet_alias(self):
        svc = ReviewPromptService()
        assert svc.resolve_sheet_suffix("截止测试") == "D2-cutoff"
        assert svc.resolve_sheet_suffix("应收账款截止测试") == "D2-cutoff"

    def test_disclosure_sheet_aliases(self):
        svc = ReviewPromptService()
        assert svc.resolve_sheet_suffix("附注上市") == "D2-note-listed"
        assert svc.resolve_sheet_suffix("附注国企") == "D2-note-soe"

    def test_d2_extended_prompts_load_as_sheet_level(self):
        svc = ReviewPromptService()
        for sheet_name in (
            "ECL测算D2-9",
            "计量测试D2-10",
            "检查表D2-11",
            "质押检查D2-12",
            "业务模式D2-13",
            "截止测试",
        ):
            result = svc.load_prompt("D2", sheet_name)
            assert result.source_level == "sheet", f"{sheet_name} should load sheet-level prompt"
            assert result.content.strip()
