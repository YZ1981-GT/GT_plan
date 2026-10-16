"""Phase 4 测试：章节定位与 preview（第 23 组起上传 / 知识库按章节树逐级定位）。"""

from __future__ import annotations

import hashlib
import uuid

import pytest

from app.services.note_document_parser import ParsedSection
from app.services.note_text_batch_service import (
    SourceContext,
    build_preview,
    locate_sources,
    match_sections,
)


# ── 夹具：来源标题树 + 目标章节树 ─────────────────────────────────────────

def _src(sid: str, title: str, level: int = 1, html: str | None = None) -> ParsedSection:
    return ParsedSection(source_id=sid, title=title, level=level,
                         html=f"<p>{title}内容</p>" if html is None else html)


def _tgt(note_section: str, title: str, *, parent: dict | None = None, kind: str = "narrative",
         text: str = "") -> dict:
    return {
        "id": uuid.uuid4(),
        "section_id": f"sec-{note_section}",
        "note_section": note_section,
        "section_title": title,
        "level": 2 if parent else 1,
        "parent_section_id": parent["section_id"] if parent else None,
        "sort_index": 0,
        "content_type": "text",
        "status": "draft",
        "is_stale": False,
        "updated_at": None,
        "text_content": text,
        "content_hash": hashlib.sha256(text.encode()).hexdigest(),
        "section_kind": kind,
        "chapter_title": (parent or {}).get("section_title"),
    }


def _chapter(code: str, title: str) -> dict:
    return _tgt(code, title, kind="container")


def _locate(sources, targets, **kw):
    return locate_sources(sources, targets, **kw)


def _by_id(matches):
    return {m.source_id: m for m in matches}


# ── 定位 ─────────────────────────────────────────────────────────────────

class TestLocate:
    def test_chapter_body_lands_on_same_named_leaf_and_is_only_candidate(self):
        """一级章「公司基本情况」定位到章，章正文落到其下同名正文节；外部来源标题定位只是候选（AC-3.3）。"""
        ch = _chapter("一", "公司基本情况")
        leaf = _tgt("一、1", "公司基本情况", parent=ch)
        _sources, matches, _s = _locate([_src("s1", "一、公司基本情况")], [ch, leaf])
        m = matches[0]
        assert (m.target_note_id, m.match_kind, m.confidence) == (leaf["id"], "chapter_body", "candidate")

    def test_alias_within_located_chapter(self):
        """显式别名（研究开发支出 ↔ 研发支出）只在已定位章内找，仍是候选。"""
        ch = _chapter("八", "财务报表主要项目注释")
        leaf = _tgt("八、70", "研发支出", parent=ch)
        sources = [_src("c", "财务报表主要项目注释", 1, ""), _src("s1", "研究开发支出", 3)]
        m = _by_id(_locate(sources, [ch, leaf])[1])["s1"]
        assert (m.target_note_id, m.match_kind, m.confidence) == (leaf["id"], "tree_path", "candidate")

    def test_whitespace_normalized_title(self):
        ch = _chapter("四", "重要会计政策、会计估计")
        leaf = _tgt("四、1", "重要会计政策概述", parent=ch)
        sources = [_src("c", "重要会计政策、会计估计", 1, ""), _src("s1", "    重要会计政策概述    ", 3)]
        m = _by_id(_locate(sources, [ch, leaf])[1])["s1"]
        assert (m.target_note_id, m.match_kind) == (leaf["id"], "tree_path")

    def test_not_found_in_chapter_is_manual_and_names_the_chapter(self):
        ch = _chapter("八", "财务报表主要项目注释")
        leaf = _tgt("八、1", "货币资金", parent=ch)
        sources = [_src("c", "财务报表主要项目注释", 1, ""), _src("s1", "完全不相关的标题", 3)]
        m = _by_id(_locate(sources, [ch, leaf])[1])["s1"]
        assert (m.target_note_id, m.match_kind, m.confidence) == (None, "tree_unmatched", "manual_required")
        assert "八 财务报表主要项目注释" in m.evidence

    def test_manual_write_mapping(self):
        ch = _chapter("八", "财务报表主要项目注释")
        leaf = _tgt("八、1", "货币资金", parent=ch)
        sources = [_src("s1", "自定义标题")]
        m = _locate(sources, [ch, leaf], manual_mappings={"s1": leaf["id"]})[1][0]
        assert (m.target_note_id, m.match_kind, m.confidence) == (leaf["id"], "manual", "confirmed")

    def test_two_sources_same_target_both_need_confirmation(self):
        """AC-3.4：同一目标不能被两个来源抢；全部人工确认，不先到先得。"""
        ch = _chapter("八", "财务报表主要项目注释")
        leaf = _tgt("八、1", "货币资金", parent=ch)
        sources = [_src("c", "财务报表主要项目注释", 1, ""), _src("s1", "货币资金", 3), _src("s2", "货币资金", 3)]
        by = _by_id(_locate(sources, [ch, leaf])[1])
        assert by["s1"].match_kind == by["s2"].match_kind == "conflict"
        assert by["s1"].target_note_id is None and by["s2"].target_note_id is None

    def test_forbidden_chapter_pair_never_located(self):
        """禁止对：「财务报表主要项目注释」不得定位到「母公司财务报表主要项目注释」。"""
        ch = _chapter("十二", "母公司财务报表主要项目注释")
        m = _locate([_src("s1", "财务报表主要项目注释", 1, "")], [ch])[1][0]
        assert (m.target_note_id, m.confidence) == (None, "manual_required")

    def test_upload_kind_is_rejected_by_template_matcher(self):
        """上传 / 知识库不得走回模板匹配器（按标题全局找）。"""
        with pytest.raises(ValueError, match="章节树"):
            match_sections([_src("s1", "货币资金")], [], source_context=SourceContext(kind="upload"))


# ── Preview ──────────────────────────────────────────────────────────────

def _company_tree(text: str = ""):
    ch = _chapter("一", "公司基本情况")
    leaf = _tgt("一、1", "公司基本情况", parent=ch, text=text)
    return [ch, leaf], leaf


def _preview(sources, targets, **kw):
    srcs, matches, structural = locate_sources(sources, targets)
    return build_preview(srcs, targets, matches, structural_ids=structural, **kw)


class TestBuildPreview:
    def test_basic_preview(self):
        targets, leaf = _company_tree()
        preview = _preview([_src("s1", "一、公司基本情况")], targets)
        assert preview["preview_digest"]
        assert len(preview["items"]) == 1
        item = preview["items"][0]
        assert item["target_note_id"] == str(leaf["id"]) and item["proposed_html"] and item["proposed_hash"]
        assert preview["summary"]["total"] == 1

    def test_variable_replacement_in_preview(self):
        targets, _leaf = _company_tree()
        src = ParsedSection(source_id="s1", title="一、公司基本情况", level=1, html="<p>{公司名称}成立于{年度}年。</p>")
        item = _preview([src], targets, target_vars={"company_name": "目标公司", "year": "2025"})["items"][0]
        assert "目标公司" in item["proposed_html"] and "2025" in item["proposed_html"]
        assert len(item["replacements"]) == 2

    def test_unmatched_is_unavailable_with_located_reason(self):
        targets, _leaf = _company_tree()
        preview = _preview([_src("s1", "不存在的标题")], targets)
        item = preview["items"][0]
        assert item["category"] == "unavailable" and "一级章里找不到「不存在的标题」" in item["unavailable_reason"]
        assert preview["summary"]["unavailable"] == 1

    def test_existing_content_is_review(self):
        targets, _leaf = _company_tree("<p>已有内容</p>")
        assert _preview([_src("s1", "一、公司基本情况")], targets)["items"][0]["category"] == "review"

    def test_digest_deterministic(self):
        targets, _leaf = _company_tree()
        sources = [_src("s1", "一、公司基本情况")]
        assert _preview(sources, targets)["preview_digest"] == _preview(sources, targets)["preview_digest"]

    def test_source_entity_risk(self):
        targets, _leaf = _company_tree()
        src = ParsedSection(source_id="s1", title="一、公司基本情况", level=1, html="<p>首汽租车股份有限公司是一家交通企业</p>")
        item = _preview([src], targets, source_entity_name="首汽租车股份有限公司")["items"][0]
        assert "source_entity" in item["quality_flags"]
