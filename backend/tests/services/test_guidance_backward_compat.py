"""排序回归 + Property 12 — note-guidance-text-separation Task 9."""

from __future__ import annotations

import inspect

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.disclosure_engine import classify_template_content
from app.services.note_offline_export_service import NoteOfflineExportService
from app.services.note_word_dynamic_styles import should_skip_empty_section


def test_load_sections_order_by_unchanged():
    """Task 9.1: guidance_text 列不改变 _load_sections 排序子句。"""
    src = inspect.getsource(NoteOfflineExportService._load_sections)
    assert "sort_order.asc().nulls_last()" in src
    assert "note_section.asc()" in src


@given(body=st.text(min_size=1, max_size=60).filter(lambda s: "应披露" not in s))
@settings(max_examples=5)
def test_property_12_empty_guidance_matches_legacy_skip(body):
    """Feature: note-guidance-text-separation, Property 12: guidance 为空等价现状"""
    note_legacy = {
        "text_content": body if body.strip() else "",
        "table_data": {},
        "is_deleted": False,
        "status": "draft",
        "is_empty": False,
    }
    note_with_empty_guidance = {**note_legacy, "guidance_text": None}
    assert should_skip_empty_section(note_legacy) == should_skip_empty_section(
        note_with_empty_guidance
    )


def test_property_12_classify_empty_template_unchanged():
    """无 guidance 模板段时 classify 返回 (None, None)。"""
    substantive, guidance = classify_template_content([], None)
    assert substantive is None
    assert guidance is None
