"""第 25 组：生成链在「无表章节」把小标题 / 短编号行当表标题丢掉（既不进正文也不进指引）。

表标题行（``#`` 标题、≤20 字的编号行）只用来给本章的表命名、推进多表游标；本章没有表时它们就是正文。
首版无表也丢：国企「十三、1」生成正文缺「2.经济利益流出不确定性的说明。」（1. 与 3. 都在），
上市「九、1 金融工具风险管理」33 个小标题全丢、正文 90 段失去层次，「三、股份支付及权益工具」生成正文为空。
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.services.disclosure_engine import (
    _flatten_paragraphs,
    _merge_bracket_blocks,
    classify_template_content,
    is_guidance_paragraph,
)
from app.services.note_section_catalog import DATA_DIR
from tests.test_disclosure_note_rag_characterization import _added_note, _minimal_template
from tests.test_disclosure_note_tree_fields import _engine


def _seed(tt: str, code: str) -> dict:
    sections = json.loads((DATA_DIR / f"note_template_{tt}.json").read_text(encoding="utf-8-sig"))["sections"]
    return next(s for s in sections if s.get("section_number") == code)


class TestClassify:
    def test_no_table_section_keeps_numbered_line_in_order(self):
        text = ["1.或有负债的种类及其形成原因，包括已贴现商业承兑汇票等形成的或有负债。",
                "2.经济利益流出不确定性的说明。",
                "3.或有负债预计产生的财务影响，以及获得补偿的可能性；无法预计的，应当说明原因。"]
        substantive, guidance, per_table = classify_template_content(text, None, [])
        assert substantive == "\n\n".join(text) and guidance is None and per_table == {}

    def test_no_table_section_keeps_markdown_subheading(self):
        substantive, guidance, _ = classify_template_content(
            ["## 风险管理目标和政策", "本公司的金融工具导致的主要风险是信用风险。", "（应披露风险管理政策。）"], None, None)
        assert substantive == "## 风险管理目标和政策\n\n本公司的金融工具导致的主要风险是信用风险。"
        assert guidance == "（应披露风险管理政策。）"

    def test_section_with_tables_still_consumes_table_titles(self):
        substantive, _, _ = classify_template_content(
            ["（1）按账龄披露", "本期无重大变化。", "## 坏账准备计提情况"], None,
            [{"name": "按账龄披露"}, {"name": "坏账准备计提情况"}])
        assert substantive == "本期无重大变化。"


@pytest.mark.parametrize("tt", ["soe", "listed"])
def test_no_table_seed_sections_lose_no_line(tt: str):
    """种子模板全部无表章节：除指引外每一段都进正文（首版国企 10 章、上市 11 章丢行）。"""
    sections = json.loads((DATA_DIR / f"note_template_{tt}.json").read_text(encoding="utf-8-sig"))["sections"]
    checked = 0
    for s in sections:
        if s.get("tables"):
            continue
        paras = _merge_bracket_blocks(_flatten_paragraphs(s.get("text_sections"), s.get("text_template")))
        body = [p for p in paras if not is_guidance_paragraph(p)]
        substantive, _, _ = classify_template_content(s.get("text_sections"), s.get("text_template"), s.get("tables"))
        got = (substantive or "").split("\n\n") if substantive else []
        assert got == body, (s.get("section_number"), [p for p in body if p not in got][:3])
        checked += bool(body)
    assert checked >= 20, "无表章节过少，判据空转"


def test_seed_contingent_liability_lines_all_present():
    substantive, _, _ = classify_template_content(*(lambda s: (s.get("text_sections"), s.get("text_template"),
                                                               s.get("tables")))(_seed("soe", "十三、1")))
    lines = [ln for ln in (substantive or "").split("\n\n") if ln[:2] in ("1.", "2.", "3.")]
    assert [ln[:2] for ln in lines] == ["1.", "2.", "3."]
    assert "2.经济利益流出不确定性的说明。" in lines


@pytest.mark.asyncio
async def test_table_template_with_headers_but_no_rows_keeps_column_meta():
    """第 12 组登记的 ``_with_column_meta`` 未定义（真库生成「十一、本公司的其他关联方情况」表格丢失）：
    并行会话 166b5e6a9 已改用 ``_carry_seed_column_meta``，此前没有测试走到这一支，补上。"""
    from tests.test_disclosure_note_rag_characterization import _make_engine

    groups = [{"group": "期末数", "start": 1, "span": 2}]
    out = await _make_engine()._build_table_data(
        uuid.uuid4(), 2025, {"headers": ["项目", "账面余额", "坏账准备"], "rows": [], "_column_groups": groups})
    assert out == {"headers": ["项目", "账面余额", "坏账准备"], "rows": [], "_column_groups": groups}


@pytest.mark.asyncio
async def test_generated_note_keeps_numbered_line():
    """生成链端到端（大模型不可用、无上年附注 ⇒ 用模板正文）：写进章节的正文含被丢的那一行。"""
    seed = _seed("soe", "十三、1")
    template = {**_minimal_template(), "note_section": "十三、1", "section_title": seed["section_title"],
                "content_type": "text", "tables": [], "text_sections": seed.get("text_sections") or [],
                "text_template": seed.get("text_template")}
    eng = _engine(template)
    await eng.generate_notes(uuid.uuid4(), 2025, "soe")
    assert "经济利益流出不确定性的说明" in (_added_note(eng).text_content or "")
