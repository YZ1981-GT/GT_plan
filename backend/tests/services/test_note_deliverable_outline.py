"""附注交付件模板轮廓与显示编号（spec deliverable-trio-generation-accuracy §1.4 / AC-2.6 / AC-3.7）。

- 一级标题位次 = 显示章号：单体国企模板没有合并专用章，内部章号「八」显示为「七」；
- 节号 = 本章保留下来的节（模板块 + 块外同级标题）的位次，无数据的节不占号；
- 报表附注列按行名找节（含「营业收入、营业成本」这类合并标题），映射按编码登记、只在标题一致时兜底。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from docx import Document

from app.services.note_deliverable_outline import (
    FsNoteRefPlan,
    TemplateNoteMatcher,
    chinese_numeral,
    load_note_template_outline,
    note_is_kept,
    number_regions,
    parse_note_template_outline,
    title_key,
)


@pytest.mark.parametrize(
    ("n", "text"), [(1, "一"), (7, "七"), (10, "十"), (11, "十一"), (16, "十六"), (20, "二十"), (23, "二十三")],
)
def test_chinese_numeral(n, text):
    assert chinese_numeral(n) == text


@pytest.mark.parametrize(
    ("raw", "key"),
    [
        ("应收账款（以下不适用的，请删除）", "应收账款"),
        ("X、数据资源", "数据资源"),
        ("三、投资性房地产【不适用】", "投资性房地产"),
        ("信用减值损失（损失以“—”号填列）", "信用减值损失"),
        ("股本（单位：万股）", "股本"),
        ("销售费用（按费用性质列示）", "销售费用"),
        ("应收票据（披露格式参考附注五、4）", "应收票据"),
        ("营业收入、营业成本", "营业收入、营业成本"),
    ],
)
def test_title_key(raw, key):
    assert title_key(raw) == key


def _synthetic_outline():
    """三个一级章；主要项目注释章有 3 个模板块 + 1 个块外同级标题；母公司章 1 块。"""
    doc = Document()

    def block(code: str, title: str):
        doc.add_paragraph(f"##SECTION:{code}##")
        doc.add_paragraph("{{seq:八}}")
        doc.add_paragraph(title, style="Heading 3")
        doc.add_paragraph("（注：编制提示）")
        doc.add_paragraph(f"##/SECTION:{code}##")

    doc.add_paragraph("公司基本情况", style="Heading 1")
    doc.add_paragraph("财务报表主要项目注释", style="Heading 1")
    block("八、1", "货币资金")
    block("八、2", "交易性金融资产")
    doc.add_paragraph("所得税费用", style="Heading 3")  # 块外同级标题（种子把该节放错章，模板没打标记）
    doc.add_paragraph("本表说明", style="Heading 4")  # 更深层级：不是节
    block("八、64", "营业收入、营业成本")
    block("八、5", "应收账款（以下不适用的，请删除）")
    doc.add_paragraph("母公司财务报表的主要项目附注", style="Heading 1")
    block("十二、应收账款", "应收账款")
    return parse_note_template_outline(doc)


def test_outline_chapters_regions_and_display_map():
    ol = _synthetic_outline()
    assert ol.chapters == ["公司基本情况", "财务报表主要项目注释", "母公司财务报表的主要项目附注"]
    assert ol.main_chapter_pos == 2 and ol.parent_chapter_pos == 3
    assert ol.chapter_display() == {"八": "二", "十二": "三"}
    main = ol.regions_in(2)
    assert [(r.code, r.key) for r in main] == [
        ("八、1", "货币资金"), ("八、2", "交易性金融资产"), (None, "所得税费用"),
        ("八、64", "营业收入、营业成本"), ("八、5", "应收账款"),
    ]


def test_number_regions_skips_unkept_and_restarts_per_chapter():
    ol = _synthetic_outline()
    kept = {"八、1", None, "八、5", "十二、应收账款"}  # 交易性金融资产 / 营业收入无数据
    numbers = number_regions(ol, lambda r: r.code in kept)
    main = {r.key: numbers.get(r.order) for r in ol.regions_in(2)}
    assert main == {
        "货币资金": "二、1",
        "交易性金融资产": None,
        "所得税费用": "二、2",
        "营业收入、营业成本": None,
        "应收账款": "二、3",
    }
    parent = ol.regions_in(3)
    assert [numbers.get(r.order) for r in parent] == ["三、1"]


def test_fs_plan_resolves_by_label_compound_parent_and_validated_hint():
    ol = _synthetic_outline()
    numbers = number_regions(ol, lambda r: True)
    plan = FsNoteRefPlan(
        outline=ol,
        numbers=numbers,
        has_notes=True,
        hints={"IS-001": ("八、64", "营业收入"), "BS-099": ("八、1", "完全不同的项目")},
    )
    assert plan.ref_for("应收账款") == "二、5"
    assert plan.ref_for("应收账款", parent=True) == "三、1"
    assert plan.ref_for("营业收入") == "二、4"  # 合并标题「营业收入、营业成本」
    assert plan.ref_for("营业成本") is None  # 只认「行名 + 连接词」开头
    assert plan.ref_for("货币资金", parent=True) is None  # 母公司章没有该节
    assert plan.ref_for("某个科目", hint_code="BS-099") is None  # 映射标题与行名不一致：不采信


def test_matcher_code_alias_sid_and_unclaimed_title():
    notes = [
        SimpleNamespace(note_section="五、1", section_id="sid-cash", section_title="货币资金"),
        SimpleNamespace(note_section="四、存货新码", section_id="sid-inv", section_title="存货"),
        SimpleNamespace(note_section="五、81", section_id="sid-tax", section_title="所得税费用"),
        SimpleNamespace(note_section="八、2", section_id="sid-fin", section_title="交易性金融资产"),
    ]
    index = [
        {"section_code": "八、1", "section_id": "sid-cash", "legacy_aliases": ["五、1"]},
        {"section_code": "四、存货", "section_id": "sid-inv", "legacy_aliases": []},
    ]
    m = TemplateNoteMatcher(notes, index, ["八、1", "四、存货", "八、2"])
    assert m.for_code("八、1").section_id == "sid-cash"  # 旧编号别名
    assert m.for_code("四、存货").section_id == "sid-inv"  # 唯一 section_id 兜底
    assert m.for_code("八、2").section_id == "sid-fin"
    assert m.for_title("所得税费用").section_id == "sid-tax"  # 块外标题：只在未被认领的附注里找
    assert m.for_title("货币资金") is None  # 已被 八、1 认领


def test_note_is_kept_matches_preset_rule():
    base = dict(is_deleted=False, status="draft", is_empty=False, table_data=None)
    assert note_is_kept(SimpleNamespace(text_content="本公司货币资金…", **base)) is True
    assert note_is_kept(SimpleNamespace(text_content="  ", **base)) is False
    assert note_is_kept(SimpleNamespace(text_content="正文", **{**base, "is_empty": True})) is False
    assert note_is_kept(SimpleNamespace(text_content="正文", **{**base, "status": "not_applicable"})) is False
    assert note_is_kept(None) is False


@pytest.mark.parametrize(
    ("std", "scope", "main_pos", "display"),
    [("soe", "standalone", 7, "七"), ("soe", "consolidated", 8, "八"), ("listed", "standalone", 5, "五")],
)
def test_real_templates_main_chapter_display(std, scope, main_pos, display):
    ol = load_note_template_outline(std, scope)
    if ol is None:
        pytest.skip("附注模板缺失")
    assert ol.main_chapter_pos == main_pos
    prefix = "八" if std == "soe" else "五"
    assert ol.chapter_display()[prefix] == display


def test_real_listed_template_loose_headings_count_in_main_chapter():
    """上市模板「公允价值变动收益」等是块外标题，同样占 Word 编号，必须进轮廓。"""
    ol = load_note_template_outline("listed", "standalone")
    if ol is None:
        pytest.skip("附注模板缺失")
    loose = {r.key for r in ol.regions_in(ol.main_chapter_pos) if r.code is None}
    assert {"公允价值变动收益", "信用减值损失", "所得税费用"} <= loose
