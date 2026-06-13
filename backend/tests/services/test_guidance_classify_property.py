"""Guidance classify / identify property tests — note-guidance-text-separation."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.disclosure_engine import (
    classify_template_content,
    identify_guidance,
    is_guidance_paragraph,
)


BODY_SAMPLES = [
    "本公司采用成本模式计量投资性房地产。",
    "本期无重大变化说明。",
    "上述会计政策自本年起执行。",
]


@given(
    guidance=st.sampled_from([
        "（注：应披露公允价值确认依据。）",
        "（说明固定资产的确认条件、分类、计价方法。）",
    ]),
    body=st.sampled_from(BODY_SAMPLES),
)
@settings(max_examples=5)
def test_property_1_generation_split_integrity(guidance, body):
    """Feature: note-guidance-text-separation, Property 1: 生成分流完整性"""
    substantive, guidance_out = classify_template_content([guidance, body], None)
    assert guidance_out == guidance
    assert substantive == body
    assert guidance not in (substantive or "")


@given(
    title=st.from_regex(r"^（[1-9]）[\u4e00-\u9fff]{2,8}$", fullmatch=True),
)
@settings(max_examples=5)
def test_property_2_table_title_not_in_text_content(title):
    """Feature: note-guidance-text-separation, Property 2: 表格标题不进正文"""
    substantive, guidance = classify_template_content([title], None)
    assert guidance is None
    assert substantive is None


@given(
    para=st.sampled_from([
        "（注：应披露公允价值确认依据。）",
        "本公司采用成本模式计量投资性房地产。",
        "（说明应评价自报告日起至少12个月持续经营能力。）",
    ]),
)
@settings(max_examples=5)
def test_property_15_generate_and_migrate_agree(para):
    """Feature: note-guidance-text-separation, Property 15: 生成与迁移指引判定一致"""
    _, guidance_from_template = classify_template_content([para], None)
    split = identify_guidance(para)
    if is_guidance_paragraph(para):
        assert guidance_from_template == para
        assert split is not None
        assert split[0] == para
    else:
        assert guidance_from_template is None
        assert split is None or split[0] == ""


@given(
    source=st.text(min_size=0, max_size=120),
)
@settings(max_examples=5)
def test_property_6_split_merge_roundtrip(source):
    """Feature: note-guidance-text-separation, Property 6: 拆分合并往返一致"""
    split = identify_guidance(source)
    if split is None:
        return
    guidance, remaining = split
    parts = source.split("\n\n")
    rebuilt: list[str] = []
    gi = ri = 0
    g_parts = guidance.split("\n\n") if guidance else []
    r_parts = remaining.split("\n\n") if remaining else []
    for part in parts:
        if is_guidance_paragraph(part.strip()):
            rebuilt.append(g_parts[gi])
            gi += 1
        else:
            rebuilt.append(r_parts[ri])
            ri += 1
    assert "\n\n".join(rebuilt) == source
