"""Phase 2 Task 14 测试：章节质量扫描与整套 quality_summary。"""

from __future__ import annotations

import pytest

from app.services.note_quality_scanner import (
    QualityFlag,
    compute_quality_summary,
    scan_section_quality,
)


class TestScanSectionQuality:
    def test_empty_text(self):
        q = scan_section_quality(text_content="")
        assert QualityFlag.EMPTY in q.flags
        assert not q.is_high_risk

    def test_none_text(self):
        q = scan_section_quality(text_content=None)
        assert QualityFlag.EMPTY in q.flags

    def test_placeholder_detected(self):
        q = scan_section_quality(text_content="<p>请在此输入公司基本情况</p>")
        assert QualityFlag.PLACEHOLDER in q.flags

    def test_draft_status(self):
        q = scan_section_quality(text_content="<p>正文</p>", status="draft")
        assert QualityFlag.DRAFT in q.flags

    def test_stale_flag(self):
        q = scan_section_quality(text_content="<p>正文</p>", is_stale=True)
        assert QualityFlag.STALE in q.flags

    def test_source_entity_name_in_text(self):
        q = scan_section_quality(
            text_content="<p>首汽租车股份有限公司是一家交通企业</p>",
            source_entity_name="首汽租车股份有限公司",
        )
        assert QualityFlag.SOURCE_ENTITY in q.flags
        assert q.is_high_risk

    def test_entity_risk_patterns(self):
        q = scan_section_quality(text_content="<p>法定代表人：张三</p>")
        assert QualityFlag.SOURCE_ENTITY in q.flags

    def test_date_detected(self):
        q = scan_section_quality(text_content="<p>截至2025年12月31日</p>")
        assert QualityFlag.DATE in q.flags

    def test_amount_detected(self):
        q = scan_section_quality(text_content="<p>金额为1,234,567.89元</p>")
        assert QualityFlag.AMOUNT in q.flags

    def test_entity_specific_title(self):
        q = scan_section_quality(
            text_content="<p>内容</p>",
            section_title="公司基本情况",
        )
        assert QualityFlag.ENTITY_SPECIFIC in q.flags
        assert q.is_high_risk

    def test_account_explanation_kind(self):
        q = scan_section_quality(
            text_content="<p>货币资金</p>",
            section_kind="account_explanation",
        )
        assert QualityFlag.ACCOUNT_EXPLANATION in q.flags
        assert q.is_high_risk

    def test_clean_narrative(self):
        q = scan_section_quality(
            text_content="<p>本公司按照企业会计准则的规定编制财务报表。</p>",
            status="confirmed",
            section_kind="narrative",
            section_title="重要会计政策",
        )
        assert QualityFlag.EMPTY not in q.flags
        assert not q.is_high_risk


class TestComputeQualitySummary:
    def test_empty_list(self):
        s = compute_quality_summary([])
        assert s["total"] == 0

    def test_mixed_qualities(self):
        qualities = [
            scan_section_quality(text_content="<p>正文</p>", status="draft"),
            scan_section_quality(text_content=""),
            scan_section_quality(
                text_content="<p>有内容</p>",
                section_kind="account_explanation",
            ),
        ]
        s = compute_quality_summary(qualities)
        assert s["total"] == 3
        assert s["with_content"] == 2
        assert s["empty"] == 1
        assert s["draft"] == 1
        assert s["account_explanation"] == 1
        assert s["high_risk"] == 1

    def test_risk_does_not_remove_sections(self):
        """风险标志只影响分组，不从全套中删除章节。"""
        qualities = [
            scan_section_quality(
                text_content="<p>内容</p>",
                section_kind="account_explanation",
                section_title="公司基本情况",
                source_entity_name="测试公司",
            ),
        ]
        s = compute_quality_summary(qualities)
        assert s["total"] == 1
        assert s["with_content"] == 1
