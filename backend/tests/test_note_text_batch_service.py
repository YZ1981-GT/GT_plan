"""Phase 4 测试：章节读取、统一匹配与 preview。"""

from __future__ import annotations

import hashlib
import uuid

import pytest

from app.services.note_document_parser import ParsedSection
from app.services.note_text_batch_service import (
    MatchResult,
    build_preview,
    match_sections,
)


# ── 匹配器测试 ──────────────────────────────────────────────────────────

def _src(sid: str, title: str) -> ParsedSection:
    return ParsedSection(source_id=sid, title=title, html=f"<p>{title}内容</p>")


def _tgt(note_section: str, title: str, *, text: str = "") -> dict:
    tid = uuid.uuid4()
    return {
        "id": tid,
        "section_id": None,
        "note_section": note_section,
        "section_title": title,
        "level": 2,
        "parent_section_id": None,
        "sort_index": 0,
        "content_type": "text",
        "status": "draft",
        "is_stale": False,
        "updated_at": None,
        "text_content": text,
        "content_hash": hashlib.sha256(text.encode()).hexdigest(),
        "section_kind": "narrative",
    }


class TestMatchSections:
    def test_exact_section_match(self):
        sources = [_src("s1", "一、公司基本情况")]
        targets = [_tgt("一、公司基本情况", "公司基本情况")]
        results = match_sections(sources, targets)
        # 第二轮复盘 R-07：外部来源（上传）没有章节编号，标题一致只是候选（AC-3.3）
        assert results[0].target_note_id == targets[0]["id"]
        assert results[0].confidence == "candidate"

    def test_alias_match(self):
        """显式别名匹配（研究开发支出 ↔ 研发支出）：外部来源同样只到候选。"""
        sources = [_src("s1", "研究开发支出")]
        targets = [_tgt("研发支出", "研发支出")]
        results = match_sections(sources, targets)
        assert results[0].confidence == "candidate"
        assert results[0].match_kind == "alias"

    def test_title_exact_candidate(self):
        """首轮此处把断言降级成 confirmed（注释称「也是正确行为」）——违反 AC-3.3，已纠正。"""
        sources = [_src("s1", "    重要会计政策概述    ")]
        targets = [_tgt("四、重要会计政策", "重要会计政策概述")]
        results = match_sections(sources, targets)
        assert results[0].target_note_id == targets[0]["id"]
        assert (results[0].confidence, results[0].match_kind) == ("candidate", "title_exact")

    def test_unmatched(self):
        sources = [_src("s1", "完全不相关的标题")]
        targets = [_tgt("一、1", "货币资金")]
        results = match_sections(sources, targets)
        assert results[0].confidence == "manual_required"
        assert results[0].target_note_id is None

    def test_manual_mapping(self):
        sources = [_src("s1", "自定义标题")]
        t = _tgt("一、1", "货币资金")
        results = match_sections(sources, [t], manual_mappings={"s1": t["id"]})
        assert results[0].confidence == "confirmed"
        assert results[0].match_kind == "manual"

    def test_one_to_one_constraint(self):
        """同一目标不能被两个来源匹配。"""
        sources = [_src("s1", "一、1 货币资金"), _src("s2", "一、1 货币资金")]
        t = _tgt("一、1 货币资金", "货币资金")
        results = match_sections(sources, [t])
        matched = [r for r in results if r.target_note_id is not None]
        assert len(matched) <= 1

    def test_forbidden_pair_not_matched(self):
        """禁止匹配对不会自动匹配。"""
        sources = [_src("s1", "财务报表主要项目注释")]
        targets = [_tgt("母公司财务报表主要项目注释", "母公司财务报表主要项目注释")]
        results = match_sections(sources, targets)
        # 禁止对 → alias_match 返回 False → 走标题精确（也不等）→ manual_required
        assert results[0].confidence == "manual_required"


# ── Preview 测试 ─────────────────────────────────────────────────────────

class TestBuildPreview:
    def test_basic_preview(self):
        sources = [_src("s1", "一、公司基本情况")]
        targets = [_tgt("一、公司基本情况", "公司基本情况")]
        matches = match_sections(sources, targets)
        preview = build_preview(sources, targets, matches)

        assert preview["preview_digest"]
        assert len(preview["items"]) == 1
        assert preview["items"][0]["proposed_html"]
        assert preview["items"][0]["proposed_hash"]
        assert preview["summary"]["total"] == 1

    def test_variable_replacement_in_preview(self):
        src = ParsedSection(
            source_id="s1",
            title="一、公司基本情况",
            html="<p>{公司名称}成立于{年度}年。</p>",
        )
        targets = [_tgt("一、公司基本情况", "公司基本情况")]
        matches = match_sections([src], targets)
        preview = build_preview(
            [src], targets, matches,
            target_vars={"company_name": "目标公司", "year": "2025"},
        )
        item = preview["items"][0]
        assert "目标公司" in item["proposed_html"]
        assert "2025" in item["proposed_html"]
        assert len(item["replacements"]) == 2

    def test_unmatched_is_unavailable(self):
        src = _src("s1", "不存在的标题")
        targets = [_tgt("一、1", "货币资金")]
        matches = match_sections([src], targets)
        preview = build_preview([src], targets, matches)
        assert preview["items"][0]["category"] == "unavailable"
        assert preview["summary"]["unavailable"] == 1

    def test_existing_content_is_review(self):
        src = _src("s1", "一、公司基本情况")
        targets = [_tgt("一、公司基本情况", "公司基本情况", text="<p>已有内容</p>")]
        matches = match_sections([src], targets)
        preview = build_preview([src], targets, matches)
        assert preview["items"][0]["category"] == "review"

    def test_digest_deterministic(self):
        sources = [_src("s1", "一、公司基本情况")]
        targets = [_tgt("一、公司基本情况", "公司基本情况")]
        matches = match_sections(sources, targets)
        p1 = build_preview(sources, targets, matches)
        p2 = build_preview(sources, targets, matches)
        assert p1["preview_digest"] == p2["preview_digest"]

    def test_source_entity_risk(self):
        src = ParsedSection(
            source_id="s1",
            title="一、公司基本情况",
            html="<p>首汽租车股份有限公司是一家交通企业</p>",
        )
        targets = [_tgt("一、公司基本情况", "公司基本情况")]
        matches = match_sections([src], targets)
        preview = build_preview(
            [src], targets, matches,
            source_entity_name="首汽租车股份有限公司",
        )
        item = preview["items"][0]
        assert "source_entity" in item["quality_flags"]
