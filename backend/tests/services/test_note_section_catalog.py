"""附注章节目录 — 统一对齐层测试."""

import pytest

from app.services.note_section_catalog import (
    build_variant_key,
    detect_heading_level,
    filter_template_sections,
    normalize_section_code,
    normalize_report_scope,
    section_applies_to_scope,
    word_template_relpath,
)


def test_normalize_report_scope():
    assert normalize_report_scope(None) == "standalone"
    assert normalize_report_scope("consolidated") == "consolidated"
    assert normalize_report_scope("INVALID") == "standalone"


def test_build_variant_key():
    assert build_variant_key("soe", "standalone") == "soe_standalone"
    assert build_variant_key("listed", "consolidated") == "listed_consolidated"


def test_section_applies_consolidated_only():
    sec = {"section_number": "七、1", "scope": "consolidated_only"}
    assert section_applies_to_scope(sec, "consolidated") is True
    assert section_applies_to_scope(sec, "standalone") is False
    assert section_applies_to_scope(sec, "both") is False  # both is not a report_scope


def test_section_applies_both():
    sec = {"section_number": "八、1", "scope": "both"}
    assert section_applies_to_scope(sec, "standalone") is True
    assert section_applies_to_scope(sec, "consolidated") is True


def test_filter_template_sections():
    sections = [
        {"section_number": "八、1", "scope": "both"},
        {"section_number": "七、1", "scope": "consolidated_only"},
    ]
    standalone = filter_template_sections(sections, "standalone")
    assert len(standalone) == 1
    assert standalone[0]["section_number"] == "八、1"
    consolidated = filter_template_sections(sections, "consolidated")
    assert len(consolidated) == 2


def test_normalize_section_code_soe_legacy():
    assert normalize_section_code("五、1", template_type="soe") == "八、1"
    assert normalize_section_code("五、1", template_type="listed") == "五、1"
    assert normalize_section_code("八、1", template_type="soe") == "八、1"


@pytest.mark.parametrize(
    "code,level",
    [
        ("一", 1),
        ("八", 1),
        ("八、1", 2),
        ("一、1", 2),
        ("四、会计期间", 2),
    ],
)
def test_detect_heading_level(code, level):
    assert detect_heading_level(code) == level


def test_word_template_relpath():
    assert word_template_relpath("soe_standalone") == "disclosure_notes/soe_standalone.docx"
