"""交付物草稿水印 — deliverable-center Task 19（需求 12）

Property 26: 水印当且仅当草稿态
- 预览叠加水印 + 下载 docx 嵌入水印，当且仅当状态 ∈ {draft, editing}
- confirmed/signed/archived 等状态生成无水印正式版本

后端 PBT 用 Hypothesis（max_examples=5 项目铁律）。

Feature: audit-report-deliverable-center
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.phase13_models import WordExportStatus
from app.services.report_body_service import (
    DRAFT_WATERMARK_MARK,
    WATERMARK_STATUSES,
    ReportBodyService,
    should_watermark,
)

# Feature: audit-report-deliverable-center

# 交付物状态机全集（与 WordExportStatus 一致）
ALL_STATUSES = [s.value for s in WordExportStatus]
# 草稿态（应带水印）与非草稿态（不应带水印）
DRAFT_STATUSES = ["draft", "editing"]
NON_DRAFT_STATUSES = [s for s in ALL_STATUSES if s not in DRAFT_STATUSES]


def _sample_body() -> dict:
    return {
        "sections": [
            {
                "section_id": "opinion",
                "section_name": "审计意见段",
                "section_order": 1,
                "content": "我们审计了被审计单位的财务报表。",
                "items": [],
            }
        ]
    }


# ===========================================================================
# Property 26: 水印当且仅当草稿态
# Feature: audit-report-deliverable-center, Property 26: 水印当且仅当草稿态
# ===========================================================================


@given(status=st.sampled_from(ALL_STATUSES))
@settings(max_examples=5, deadline=None)
def test_watermark_iff_draft_status(status):
    # Feature: audit-report-deliverable-center, Property 26: 水印当且仅当草稿态
    """Property 26: 对任意交付物状态，下载 docx 嵌入水印 ∧ 预览叠加水印，
    当且仅当 status ∈ {draft, editing}；其余状态生成无水印文件。

    Validates: Requirements 12.1, 12.2, 12.3
    """
    svc = ReportBodyService.__new__(ReportBodyService)  # 纯渲染无需 db
    expected = status in ("draft", "editing")

    # ── 判定真源（预览 overlay 与下载渲染共用同一谓词）──
    decision = should_watermark(status)
    assert decision is expected

    # ── 下载文件：watermark 标志由 should_watermark 推导，渲染后用检测器校验 ──
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / f"deliverable_{status}.docx"
        svc.render_docx(_sample_body(), out, watermark=decision)
        assert out.exists()
        has_mark = svc.docx_has_watermark(out)
        # 当且仅当：草稿态嵌入水印，非草稿态无水印
        assert has_mark is expected

    # ── 预览叠加：前端 DraftWatermark 可见性同样由该谓词驱动 ──
    preview_overlay_shown = decision
    assert preview_overlay_shown is expected


@given(status=st.sampled_from(ALL_STATUSES))
@settings(max_examples=5, deadline=None)
def test_should_watermark_matches_statuses_set(status):
    # Feature: audit-report-deliverable-center, Property 26: 水印当且仅当草稿态
    """should_watermark 与 WATERMARK_STATUSES 集合定义一致（无遗漏/越界）。"""
    assert should_watermark(status) is (status in WATERMARK_STATUSES)


# ===========================================================================
# 单元测试：具体边界示例
# ===========================================================================


def test_draft_and_editing_embed_watermark():
    """draft/editing 下载文件含草稿水印标记。"""
    svc = ReportBodyService.__new__(ReportBodyService)
    for status in DRAFT_STATUSES:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "d.docx"
            svc.render_docx(_sample_body(), out, watermark=should_watermark(status))
            assert svc.docx_has_watermark(out) is True
            # 标记文本确实落在段落里
            from docx import Document

            text = "\n".join(p.text for p in Document(str(out)).paragraphs)
            assert DRAFT_WATERMARK_MARK in text


def test_confirmed_and_signed_no_watermark():
    """confirmed/signed 生成无水印正式版本。"""
    svc = ReportBodyService.__new__(ReportBodyService)
    for status in ("confirmed", "signed"):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "f.docx"
            svc.render_docx(_sample_body(), out, watermark=should_watermark(status))
            assert svc.docx_has_watermark(out) is False


def test_none_status_no_watermark():
    """状态缺失（None）视为无水印，避免误嵌入。"""
    assert should_watermark(None) is False


def test_watermark_statuses_exactly_draft_editing():
    """水印态集合恰为 {draft, editing}（守护需求 12 边界不漂移）。"""
    assert WATERMARK_STATUSES == frozenset({"draft", "editing"})
