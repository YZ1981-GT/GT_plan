"""标题尾部提示与国企↔上市同名多节配对守卫。

spec: disclosure-note-template-word-realignment Phase 8 / Task 32
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from docx import Document

from app.services.note_conversion_service import NoteConversionService
from app.services.note_template_block_fill import strip_title_guidance
from app.services.note_template_diff import compute_diff_from_templates
from app.services.note_title_hint import merge_title_hint_guidance, split_title_hint
from tests.services.test_note_conversion_section_mapping_production import (
    PROJECT,
    YEAR,
    FakeSession,
    make_note,
)

DATA = Path(__file__).resolve().parents[1] / "data"


def _templates() -> dict[str, list[dict]]:
    return {
        side: json.loads((DATA / f"note_template_{side}.json").read_text(encoding="utf-8"))["sections"]
        for side in ("soe", "listed")
    }


def _by_number(sections: list[dict]) -> dict[str, dict]:
    return {s["section_number"]: s for s in sections}


@pytest.mark.parametrize(
    ("raw", "title", "hint"),
    [
        ("应收账款（以下不适用的，请删除）", "应收账款", "以下不适用的，请删除"),
        ("投资收益【下表中不适用的项目，删除】", "投资收益", "下表中不适用的项目，删除"),
        ("收入（按行业）【没有数据可删除】", "收入", "按行业\n没有数据可删除"),
        ("股本（单位：万股）", "股本", "单位：万股"),
        ("公司（企业）基本情况", "公司（企业）基本情况", None),
        ("（1）一年内到期的长期借款", "（1）一年内到期的长期借款", None),
        ("（整段都是提示）", "（整段都是提示）", None),
    ],
)
def test_split_title_hint_only_strips_trailing_brackets(raw: str, title: str, hint: str | None) -> None:
    assert split_title_hint(raw) == (title, hint)


def test_title_hint_uses_guidance_channel_without_entering_title_or_body() -> None:
    assert merge_title_hint_guidance("没有数据可删除", "请核对本期金额") == (
        "标题提示：没有数据可删除\n\n请核对本期金额"
    )
    assert merge_title_hint_guidance("没有数据可删除", "提示：没有数据可删除") == "提示：没有数据可删除"
    assert merge_title_hint_guidance(None, None) is None


def test_delivery_title_uses_the_same_stripping_rule() -> None:
    doc = Document()
    paragraph = doc.add_paragraph("资产负债表日后利润分配情况（只写现金分配，若仅有转增，则不写）")
    assert strip_title_guidance(paragraph._p) is True
    assert paragraph.text == "资产负债表日后利润分配情况"


def test_real_seed_titles_are_clean_and_hints_are_preserved() -> None:
    templates = _templates()
    soe = _by_number(templates["soe"])
    listed = _by_number(templates["listed"])

    assert soe["八、70"]["section_title"] == "投资收益"
    assert soe["八、70"]["title_hint"] == "下表中不适用的项目，删除"
    assert soe["八、94"]["section_title"] == "一般风险准备"  # 用户明确保留
    assert listed["十四、资产负债表日后利润分配情况（只写现金分配，若仅有转增，则不写）"]["section_title"] == (
        "资产负债表日后利润分配情况"
    )
    assert listed["十四、资产负债表日后利润分配情况（只写现金分配，若仅有转增，则不写）"]["title_hint"] == (
        "只写现金分配，若仅有转增，则不写"
    )
    assert listed["十六"]["section_title"] == "公司财务报表主要项目注释"
    revenue = listed["十六、营业收入与营业成本"]
    assert revenue["section_title"] == "营业收入和营业成本"
    assert revenue["title_hint"] == "披露格式参考附注五、62"


def test_every_titled_section_appears_in_exactly_one_diff_bucket() -> None:
    templates = _templates()
    diff = compute_diff_from_templates(templates["soe"], templates["listed"])
    seen = {
        "soe": [c["soe_section_id"] for c in diff["common_sections"]]
        + [e["section_id"] for e in diff["soe_only_sections"]],
        "listed": [c["listed_section_id"] for c in diff["common_sections"]]
        + [e["section_id"] for e in diff["listed_only_sections"]],
    }
    for side in ("soe", "listed"):
        expected = [s["section_id"] for s in templates[side] if s.get("section_title")]
        assert len(seen[side]) == len(set(seen[side])) == len(expected)
        assert set(seen[side]) == set(expected)


def test_duplicate_titles_pair_by_chapter_kind_not_first_occurrence() -> None:
    templates = _templates()
    diff = compute_diff_from_templates(templates["soe"], templates["listed"])
    numbers = {
        side: {s["section_id"]: s["section_number"] for s in templates[side]}
        for side in ("soe", "listed")
    }
    pairs = {
        (numbers["soe"][c["soe_section_id"]], numbers["listed"][c["listed_section_id"]])
        for c in diff["common_sections"]
    }
    assert ("八、22", "五、22") in pairs
    assert ("十二、投资收益", "十六、投资收益（注：以") in pairs
    assert ("四、应付债券", "五、46") not in pairs
    assert ("十二、投资收益", "五、69") not in pairs


@pytest.mark.asyncio
async def test_alias_conversion_updates_target_title_and_keeps_values() -> None:
    templates = _templates()
    diff = compute_diff_from_templates(templates["soe"], templates["listed"])
    plan = NoteConversionService(FakeSession([]))._build_section_mapping_plan(diff, "soe", "listed")
    soe = _by_number(templates["soe"])
    listed = _by_number(templates["listed"])
    src = soe["十二、营业收入与营业成本"]
    target = listed["十六、营业收入与营业成本"]
    pair = plan["pairs"][src["section_id"]]
    assert pair["target_sid"] == target["section_id"]
    assert pair["target_title"] == "营业收入和营业成本"

    note = make_note(
        section_id=src["section_id"],
        note_section=src["section_number"],
        section_title=src["section_title"],
        table_data={"rows": [{"label": "主营业务", "values": [100]}]},
    )
    note.account_name = src["section_title"]
    service = NoteConversionService(FakeSession([note]))
    result = await service._map_disclosure_notes(PROJECT, YEAR, "soe", "listed")
    assert result["failed"] == []
    assert note.section_id == target["section_id"]
    assert note.note_section == target["section_number"]
    assert note.section_title == note.account_name == "营业收入和营业成本"
    assert note.table_data == {"rows": [{"label": "主营业务", "values": [100]}]}


@pytest.mark.asyncio
async def test_standard_template_loader_preserves_title_hint(monkeypatch) -> None:
    """标准种子投影不得丢标题提示，否则生成链永远看不见 Phase 8 的修复。"""
    from unittest.mock import AsyncMock, MagicMock
    from uuid import uuid4

    from app.services.disclosure_engine import DisclosureEngine
    from app.services.note_custom_template_service import NoteCustomTemplateService

    monkeypatch.setattr(NoteCustomTemplateService, "load_custom_template", AsyncMock(return_value=None))
    templates = await DisclosureEngine(MagicMock())._load_templates(uuid4(), "soe", "standalone")
    investment_income = next(template for template in templates if template["note_section"] == "八、70")
    assert investment_income["section_title"] == "投资收益"
    assert investment_income["title_hint"] == "下表中不适用的项目，删除"
