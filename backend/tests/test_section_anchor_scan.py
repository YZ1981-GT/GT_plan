"""锚点区间扫描与块定位降级链测试 — deliverable-lineage-wiring-and-writeback-closure Task 1.1

覆盖：
- Property 4：锚点写入 ↔ 扫描互逆（标记清理后仍可定位）
- Property 5：块定位降级链单调（anchor / marker / none 三态均不抛异常）
- Rendered_Block_Hash 口径（排除 ## 标记行、规范化、对改动敏感）
- 反向自检：内容控件开启后仅看 body 级会把整节看成单个 sdt（故必须展平）

本层用合成 docx 是合法的（design §Testing Strategy 第 1 层）；**真实链路验收在 Task 11**。
"""

from __future__ import annotations

from io import BytesIO

import pytest
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.section_anchor_utils import (
    SectionBlock,
    anchor_block_content_host,
    anchor_name,
    block_text_hash,
    block_text_of,
    normalize_block_text,
    resolve_section_blocks,
    scan_anchor_blocks,
    write_section_anchors,
)
from app.services.word_doc_utils import remove_section_markers, scan_section_blocks

ALL_CODES = ["八、1", "八、2", "五、1", "八、22"]


# ─── 夹具 ────────────────────────────────────────────────────────────────────


def _build_doc(sections: dict[str, list[str]]) -> Document:
    """构建含 ``##SECTION:code##`` 块的合成 docx（每节若干正文段落）。"""
    doc = Document()
    for code, lines in sections.items():
        doc.add_paragraph(f"##SECTION:{code}##")
        for line in lines:
            doc.add_paragraph(line)
        doc.add_paragraph(f"##/SECTION:{code}##")
    return doc


def _roundtrip(doc: Document) -> Document:
    """序列化 → 反序列化（模拟落盘 / OnlyOffice 往返后再由 python-docx 读回）。"""
    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return Document(buf)


def _write_anchors(doc: Document, kept_codes: list[str]) -> dict[str, str]:
    blocks = {b.section_code: b for b in scan_section_blocks(doc)}
    kept_blocks = [
        SectionBlock(
            section_code=code,
            open_el=blocks[code].open_el,
            close_el=blocks[code].close_el,
        )
        for code in kept_codes
        if code in blocks
    ]
    return write_section_anchors(doc, kept_blocks)


def _all_text(doc: Document) -> list[str]:
    return [p.text for p in doc.paragraphs]


# ─── Property 4：写入 ↔ 扫描互逆 ─────────────────────────────────────────────


@given(kept=st.lists(st.sampled_from(ALL_CODES), min_size=1, max_size=4, unique=True))
@settings(max_examples=5, deadline=None)
def test_property_4_anchor_scan_is_inverse_of_write(kept):
    # Feature: deliverable-lineage-wiring-and-writeback-closure, Property 4
    """写锚点 → 清标记 → 往返 → scan_anchor_blocks 得到的 code 集合 == kept。"""
    sections = {code: [f"{code} 正文一", f"{code} 正文二"] for code in ALL_CODES}
    doc = _build_doc(sections)
    _write_anchors(doc, kept)
    remove_section_markers(doc)
    doc = _roundtrip(doc)

    blocks = scan_anchor_blocks(doc)
    assert {b.section_code for b in blocks} == set(kept)
    for b in blocks:
        assert b.anchor_name == anchor_name(b.section_code)
        # 区间内容元素非空且不含标记行
        texts = block_text_of(b.elements)
        assert b.section_code in texts
        assert "##" not in texts


def test_anchor_scan_covers_exactly_its_own_content():
    """锚点区间只覆盖本章节内容，不串到邻节。"""
    doc = _build_doc({"八、1": ["甲"], "八、2": ["乙"]})
    _write_anchors(doc, ["八、1", "八、2"])
    remove_section_markers(doc)
    doc = _roundtrip(doc)

    by_code = {b.section_code: b for b in scan_anchor_blocks(doc)}
    assert block_text_of(by_code["八、1"].elements) == "甲"
    assert block_text_of(by_code["八、2"].elements) == "乙"


def test_trimmed_sections_have_no_anchor():
    """裁剪章节不写锚点 → 扫描结果里没有它（Property 1 的扫描侧印证）。"""
    doc = _build_doc({"八、1": ["甲"], "八、2": ["乙"]})
    _write_anchors(doc, ["八、1"])
    remove_section_markers(doc)
    doc = _roundtrip(doc)

    assert {b.section_code for b in scan_anchor_blocks(doc)} == {"八、1"}


# ─── 内容控件并存 ────────────────────────────────────────────────────────────


def test_scan_works_with_content_controls_and_flattens():
    """内容控件开启后：body 级只剩一个 w:sdt，扫描须下钻取到内部段落。"""
    from app.services.content_control_injector import inject_content_controls_for_blocks

    doc = _build_doc({"八、1": ["甲一", "甲二"]})
    _write_anchors(doc, ["八、1"])
    inject_content_controls_for_blocks(doc, scan_section_blocks(doc))
    remove_section_markers(doc)
    doc = _roundtrip(doc)

    blocks = scan_anchor_blocks(doc)
    assert len(blocks) == 1
    b = blocks[0]
    # 反向自检：body 级容器是单个 sdt（只看 containers 取不到文字）
    assert len(b.containers) == 1
    assert b.containers[0].tag == qn("w:sdt")
    assert block_text_of(b.containers) == "", "containers 未展平时不应有文字（证明展平必要）"
    # 展平后拿得到内部两段
    assert block_text_of(b.elements) == "甲一\n甲二"


def test_content_host_prefers_sdt_content():
    """有内容控件时插入宿主是 sdtContent；无控件时是 body。"""
    from app.services.content_control_injector import inject_content_controls_for_blocks

    doc = _build_doc({"八、1": ["甲"]})
    _write_anchors(doc, ["八、1"])
    remove_section_markers(doc)
    doc = _roundtrip(doc)
    block = scan_anchor_blocks(doc)[0]
    host, children = anchor_block_content_host(block)
    assert host.tag == qn("w:body")
    assert len(children) == 1

    doc2 = _build_doc({"八、1": ["甲"]})
    _write_anchors(doc2, ["八、1"])
    inject_content_controls_for_blocks(doc2, scan_section_blocks(doc2))
    remove_section_markers(doc2)
    doc2 = _roundtrip(doc2)
    block2 = scan_anchor_blocks(doc2)[0]
    host2, children2 = anchor_block_content_host(block2)
    assert host2.tag == qn("w:sdtContent")
    assert len(children2) == 1


# ─── 健壮性 ──────────────────────────────────────────────────────────────────


def test_non_section_bookmarks_ignored():
    """非 sec_ 前缀书签（Word 内部 / note bookmark）不得被当章节锚点。"""
    doc = _build_doc({"八、1": ["甲"]})
    body = doc.element.body
    bm = OxmlElement("w:bookmarkStart")
    bm.set(qn("w:id"), "9001")
    bm.set(qn("w:name"), "note_八_1")
    body.insert(0, bm)
    bm_end = OxmlElement("w:bookmarkEnd")
    bm_end.set(qn("w:id"), "9001")
    body.append(bm_end)

    assert scan_anchor_blocks(doc) == []


def test_unclosed_anchor_skipped():
    """bookmarkStart 无匹配 end → 跳过，不抛异常。"""
    doc = _build_doc({"八、1": ["甲"]})
    body = doc.element.body
    bm = OxmlElement("w:bookmarkStart")
    bm.set(qn("w:id"), "1000")
    bm.set(qn("w:name"), anchor_name("八、1"))
    body.insert(0, bm)

    assert scan_anchor_blocks(doc) == []


def test_duplicate_section_code_takes_first_only():
    """同 section_code 多锚点 → 取首个，禁止静默合并成一节。"""
    doc = _build_doc({"八、1": ["甲"]})
    _write_anchors(doc, ["八、1"])
    # 再手工追加一段同名锚点区间
    body = doc.element.body
    bm = OxmlElement("w:bookmarkStart")
    bm.set(qn("w:id"), "2000")
    bm.set(qn("w:name"), anchor_name("八、1"))
    body.append(bm)
    p = doc.add_paragraph("重复节内容")
    bm_end = OxmlElement("w:bookmarkEnd")
    bm_end.set(qn("w:id"), "2000")
    body.append(bm_end)
    remove_section_markers(doc)

    blocks = scan_anchor_blocks(doc)
    assert len(blocks) == 1
    assert "重复节内容" not in block_text_of(blocks[0].elements)
    assert p is not None


def test_scan_on_empty_document_returns_empty():
    assert scan_anchor_blocks(Document()) == []


# ─── Property 5：降级链单调 ──────────────────────────────────────────────────


def test_property_5_locate_mode_anchor():
    # Feature: deliverable-lineage-wiring-and-writeback-closure, Property 5
    doc = _build_doc({"八、1": ["甲"]})
    _write_anchors(doc, ["八、1"])
    remove_section_markers(doc)
    mode, blocks = resolve_section_blocks(_roundtrip(doc))
    assert mode == "anchor"
    assert [b.section_code for b in blocks] == ["八、1"]


def test_property_5_locate_mode_marker():
    # Feature: deliverable-lineage-wiring-and-writeback-closure, Property 5
    """存量 / 中间态文档：标记仍在、无锚点 → 回退 marker。"""
    doc = _build_doc({"八、1": ["甲"]})
    mode, blocks = resolve_section_blocks(doc)
    assert mode == "marker"
    assert [b.section_code for b in blocks] == ["八、1"]


def test_property_5_locate_mode_none():
    # Feature: deliverable-lineage-wiring-and-writeback-closure, Property 5
    """接线前生成的存量交付件：标记已清、无锚点 → none 且空列表（不抛）。"""
    doc = _build_doc({"八、1": ["甲"]})
    remove_section_markers(doc)
    mode, blocks = resolve_section_blocks(_roundtrip(doc))
    assert mode == "none"
    assert blocks == []


def test_locate_mode_anchor_wins_over_marker():
    """锚点与标记同时存在（中间态）→ 优先 anchor。"""
    doc = _build_doc({"八、1": ["甲"]})
    _write_anchors(doc, ["八、1"])
    mode, _ = resolve_section_blocks(doc)
    assert mode == "anchor"


@pytest.mark.parametrize(
    "builder",
    [
        lambda: Document(),
        lambda: _build_doc({}),
        lambda: _build_doc({"八、1": []}),
    ],
)
def test_locate_never_raises_on_degenerate_docs(builder):
    mode, blocks = resolve_section_blocks(builder())
    assert mode in ("anchor", "marker", "none")
    assert isinstance(blocks, list)


# ─── Rendered_Block_Hash 口径 ────────────────────────────────────────────────


def test_block_text_excludes_markers_and_tables():
    doc = _build_doc({"八、1": ["甲"]})
    block = scan_section_blocks(doc)[0]
    # 块内含开闭标记段落，提取结果不得包含
    assert block_text_of(block.elements) == "甲"


def test_normalize_block_text_collapses_whitespace_and_blank_lines():
    assert normalize_block_text("  甲   乙 \r\n\r\n  丙  ") == "甲 乙\n丙"
    assert normalize_block_text("") == ""


def test_block_text_hash_is_deterministic_and_sensitive():
    doc_a = _build_doc({"八、1": ["甲", "乙"]})
    doc_b = _build_doc({"八、1": ["甲 ", " 乙"]})
    doc_c = _build_doc({"八、1": ["甲", "丙"]})
    ha = block_text_hash(scan_section_blocks(doc_a)[0].elements)
    hb = block_text_hash(scan_section_blocks(doc_b)[0].elements)
    hc = block_text_hash(scan_section_blocks(doc_c)[0].elements)
    assert ha == hb, "仅空白差异不应改变哈希"
    assert ha != hc, "文字改动必须改变哈希"
    assert len(ha) == 64


def test_block_text_hash_differs_from_snapshot_hash_domain():
    """反向自检：Rendered_Block_Hash 与 source_snapshot_hash 是两个哈希域。

    历史缺陷正是拿后者去比块内文字 ⇒ 永远不等。本断言钉住「二者不可互换」，
    防后来者又把 `_detect_user_edits` 改回去比 source_snapshot_hash。
    """
    from app.services.deliverable_section_state_service import (
        compute_snapshot_hash_from_parts,
    )

    doc = _build_doc({"八、1": ["甲"]})
    block_hash = block_text_hash(scan_section_blocks(doc)[0].elements)
    snapshot_hash = compute_snapshot_hash_from_parts(
        section_code="八、1",
        text_content="甲",
        table_data=None,
        audited_amounts=[],
    )
    assert block_hash != snapshot_hash
