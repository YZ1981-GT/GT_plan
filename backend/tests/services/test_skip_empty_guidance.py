"""should_skip_empty_section 与 guidance_text 无关 — note-guidance-text-separation Task 3.1/3.2."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.note_word_dynamic_styles import should_skip_empty_section


def test_skip_when_only_guidance_non_empty():
    note = {
        "text_content": "",
        "table_data": {"headers": [], "rows": []},
        "guidance_text": "（注：应披露公允价值确认依据。）",
    }
    assert should_skip_empty_section(note) is True


def test_no_skip_when_text_content_present():
    note = {
        "text_content": "本公司采用成本模式计量。",
        "table_data": {},
        "guidance_text": "（注：应披露…）",
    }
    assert should_skip_empty_section(note) is False


@given(guidance=st.text(min_size=0, max_size=80))
@settings(max_examples=5)
def test_property_3_skip_independent_of_guidance(guidance):
    """Feature: note-guidance-text-separation, Property 3: 判空与 guidance 无关"""
    base = {
        "text_content": "",
        "table_data": {"headers": [], "rows": []},
        "is_deleted": False,
        "status": "draft",
        "is_empty": False,
    }
    assert should_skip_empty_section(base) == should_skip_empty_section(
        {**base, "guidance_text": guidance}
    )
