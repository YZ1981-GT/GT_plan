"""Tests for wp_code-aware 附注 sheet-level prompt suffix resolution."""
from __future__ import annotations

from app.services.review_prompt_service import ReviewPromptService


def test_note_suffix_listed_variants():
    s = ReviewPromptService()
    assert s._resolve_note_suffix("D2", "附注上市") == "D2-note-listed"
    assert s._resolve_note_suffix("K8", "附注披露信息（上市公司）") == "K8-note-listed"
    assert s._resolve_note_suffix("N5", "附注(上市)") == "N5-note-listed"
    assert s._resolve_note_suffix("N1", "disclosure-listed") == "N1-note-listed"


def test_note_suffix_soe_variants():
    s = ReviewPromptService()
    assert s._resolve_note_suffix("K8", "附注国企") == "K8-note-soe"
    assert s._resolve_note_suffix("N5", "附注（国企）") == "N5-note-soe"
    assert s._resolve_note_suffix("N1", "disclosure-soe") == "N1-note-soe"


def test_note_suffix_single_disclosure_defaults_listed():
    s = ReviewPromptService()
    # N3 单一"附注"（无上市/国企变体）默认 note-listed
    assert s._resolve_note_suffix("N3", "附注") == "N3-note-listed"
    assert s._resolve_note_suffix("N3", "附注披露") == "N3-note-listed"


def test_note_suffix_non_note_returns_none():
    s = ReviewPromptService()
    assert s._resolve_note_suffix("K8", "审定表K8-1") is None
    assert s._resolve_note_suffix("K8", "明细表K8-2") is None
    assert s._resolve_note_suffix("K8", "") is None


def test_d2_note_still_loads_sheet_backward_compat():
    """D2 附注上市/国企 仍加载既有 sheet-level 文件（回归）。"""
    s = ReviewPromptService()
    assert s.load_prompt("D2", "附注上市").source_level == "sheet"
    assert s.load_prompt("D2", "附注国企").source_level == "sheet"
